"""EventBus — шина событий на Redis Streams.

Обеспечивает асинхронное взаимодействие между процессами (бот ↔ бэкенд)
через паттерны publish/subscribe и request-reply.

Использование:
    bus = EventBus("redis://localhost:6379/0")
    await bus.connect()

    # Publish
    await bus.publish("stream:requests", {"type": "consult", "payload": {...}})

    # Subscribe (consumer group)
    await bus.subscribe("stream:requests", "backend", handler)

    # Request-reply
    response = await bus.request_reply("stream:requests", {"type": "consult", ...}, timeout=30)

    await bus.close()
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Callable, Coroutine

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Типы
EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any] | None]]


def _make_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    reply_to: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Создать событие по протоколу шины."""
    return {
        "type": event_type,
        "payload": payload or {},
        "reply_to": reply_to or "",
        "correlation_id": correlation_id or "",
        "timestamp": time.time(),
    }


class EventBus:
    """Шина событий поверх Redis Streams."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        self._url = redis_url
        self._redis: aioredis.Redis | None = None
        self._running = False
        self._tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Подключиться к Redis."""
        if self._redis:
            return
        self._redis = aioredis.from_url(
            self._url,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        await self._redis.ping()
        self._running = True
        logger.info("EventBus: подключён к %s", self._url)

    async def close(self) -> None:
        """Остановить подписки и закрыть соединение."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self._redis:
            await self._redis.aclose()
            self._redis = None
            logger.info("EventBus: отключён")

    @property
    def connected(self) -> bool:
        return self._redis is not None and self._running

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish(self, stream: str, event: dict[str, Any]) -> str:
        """Отправить событие в stream. Возвращает message_id."""
        assert self._redis, "EventBus не подключён"
        data = {"data": json.dumps(event, ensure_ascii=False, default=str)}
        msg_id = await self._redis.xadd(stream, data)
        logger.debug("EventBus: publish → %s [%s] type=%s", stream, msg_id, event.get("type"))
        return msg_id

    # ------------------------------------------------------------------
    # Subscribe (consumer group)
    # ------------------------------------------------------------------

    async def subscribe(
        self,
        stream: str,
        group: str,
        handler: EventHandler,
        consumer: str | None = None,
    ) -> None:
        """Подписаться на stream через consumer group.

        handler получает dict события и может вернуть dict-ответ (для request-reply).
        """
        assert self._redis, "EventBus не подключён"
        consumer = consumer or f"{group}-{uuid.uuid4().hex[:8]}"

        # Создать группу (если не существует)
        try:
            await self._redis.xgroup_create(stream, group, id="0", mkstream=True)
            logger.info("EventBus: создана группа %s для %s", group, stream)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        task = asyncio.create_task(
            self._consume_loop(stream, group, consumer, handler),
            name=f"bus:{stream}:{group}",
        )
        self._tasks.append(task)
        logger.info("EventBus: подписка %s/%s на %s", group, consumer, stream)

    async def _consume_loop(
        self,
        stream: str,
        group: str,
        consumer: str,
        handler: EventHandler,
    ) -> None:
        """Цикл чтения событий из consumer group."""
        assert self._redis
        while self._running:
            try:
                messages = await self._redis.xreadgroup(
                    groupname=group,
                    consumername=consumer,
                    streams={stream: ">"},
                    count=10,
                    block=1000,  # 1 сек
                )
                if not messages:
                    continue

                for _stream_name, entries in messages:
                    for msg_id, fields in entries:
                        try:
                            event = json.loads(fields.get("data", "{}"))
                            result = await handler(event)

                            # Если есть reply_to — отправить ответ
                            if result and event.get("reply_to"):
                                reply = _make_event(
                                    event_type=f"{event.get('type', 'unknown')}_response",
                                    payload=result,
                                    correlation_id=event.get("correlation_id", ""),
                                )
                                await self.publish(event["reply_to"], reply)

                            await self._redis.xack(stream, group, msg_id)
                        except Exception:
                            logger.exception("EventBus: ошибка обработки %s", msg_id)
                            await self._redis.xack(stream, group, msg_id)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("EventBus: ошибка в consume loop %s/%s", stream, group)
                await asyncio.sleep(1)

    # ------------------------------------------------------------------
    # Request-Reply
    # ------------------------------------------------------------------

    async def request_reply(
        self,
        stream: str,
        event: dict[str, Any],
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Отправить запрос и дождаться ответа.

        Создаёт временный stream для ответа, отправляет событие с reply_to,
        ждёт ответ с таймаутом.
        """
        assert self._redis, "EventBus не подключён"
        correlation_id = uuid.uuid4().hex
        reply_stream = f"replies:{correlation_id}"

        event["reply_to"] = reply_stream
        event["correlation_id"] = correlation_id

        await self.publish(stream, event)

        # Ждём ответ
        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                remaining = max(0.1, deadline - time.time())
                block_ms = int(min(remaining, 1.0) * 1000)

                messages = await self._redis.xread(
                    streams={reply_stream: "0-0"},
                    count=1,
                    block=block_ms,
                )
                if messages:
                    for _stream_name, entries in messages:
                        for _msg_id, fields in entries:
                            response = json.loads(fields.get("data", "{}"))
                            return response.get("payload", response)
        finally:
            # Удалить временный stream
            await self._redis.delete(reply_stream)

        raise TimeoutError(f"EventBus: таймаут {timeout}с для {event.get('type')}")


def make_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Публичная фабрика событий."""
    return _make_event(event_type, payload, **kwargs)
