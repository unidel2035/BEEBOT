"""BotServiceClient — клиент для обращения бота к Backend через Redis Streams.

Бот не вызывает CRM/LLM/KB напрямую. Вместо этого публикует запросы
в Redis и получает ответы от Backend.

Использование:
    bus = EventBus(REDIS_URL)
    await bus.connect()
    client = BotServiceClient(bus)

    # Консультация
    answer = await client.consult(user_id=123, query="что такое прополис")

    # Создание заказа
    result = await client.create_order(client_id=10, items=[...])

    # Слушать события от Backend
    asyncio.create_task(client.listen_events(bot))
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from src.bus import EventBus, make_event

logger = logging.getLogger(__name__)

STREAM_REQUESTS = "stream:requests"
STREAM_EVENTS = "stream:events"
GROUP_BOT = "bot"

_DEFAULT_TIMEOUT = 30.0
_FALLBACK_TEXT = "⏳ Сервис временно недоступен. Попробуйте позже."


class BotServiceClient:
    """Клиент бота для обращения к Backend через шину."""

    def __init__(self, bus: EventBus, timeout: float = _DEFAULT_TIMEOUT):
        self._bus = bus
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Запросы к Backend (request-reply)
    # ------------------------------------------------------------------

    async def consult(
        self,
        user_id: int,
        query: str,
        history: Optional[list] = None,
        style: Optional[str] = None,
    ) -> dict:
        """Консультация: вопрос → ответ от KB + LLM."""
        return await self._request("consult", {
            "user_id": user_id,
            "query": query,
            "history": history or [],
            "style": style,
        })

    async def create_order(
        self,
        client_id: int,
        items: list[dict],
        **kwargs: Any,
    ) -> dict:
        """Создать заказ через Backend."""
        return await self._request("create_order", {
            "client_id": client_id,
            "items": items,
            **kwargs,
        })

    async def update_order_status(
        self,
        order_id: int,
        status: str,
        comment: str = "",
        role: str = "admin",
    ) -> dict:
        """Обновить статус заказа."""
        return await self._request("update_order_status", {
            "order_id": order_id,
            "status": status,
            "comment": comment,
            "role": role,
        })

    async def get_orders(
        self,
        client_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> dict:
        """Получить список заказов."""
        return await self._request("get_orders", {
            "client_id": client_id,
            "status": status,
        })

    async def get_order(self, order_id: int) -> dict:
        """Получить заказ по ID."""
        return await self._request("get_order", {"order_id": order_id})

    async def get_order_items(self, order_id: int) -> dict:
        """Получить позиции заказа."""
        return await self._request("get_order_items", {"order_id": order_id})

    async def analytics_query(self, query: str, admin_id: int) -> dict:
        """Аналитический запрос."""
        return await self._request("analytics_query", {
            "query": query,
            "admin_id": admin_id,
        })

    async def ping(self) -> dict:
        """Проверка связи с Backend."""
        return await self._request("ping", {}, timeout=5.0)

    # ------------------------------------------------------------------
    # События от Backend (subscribe)
    # ------------------------------------------------------------------

    async def listen_events(self, send_fn) -> None:
        """Слушать события от Backend и отправлять уведомления.

        Args:
            send_fn: async функция(chat_id: int, text: str) для отправки в Telegram.
        """
        async def handler(event: dict) -> None:
            event_type = event.get("type", "")
            payload = event.get("payload", {})

            try:
                if event_type == "order_status_changed":
                    tg_id = payload.get("client_tg_id")
                    if tg_id:
                        text = f"📋 Заказ {payload.get('order_number', '?')}: {payload.get('status', '?')}"
                        await send_fn(tg_id, text)

                elif event_type == "delivery_update":
                    tg_id = payload.get("client_tg_id")
                    if tg_id:
                        text = f"🚚 Заказ {payload.get('order_number', '?')}: {payload.get('tracking_status', '?')}"
                        await send_fn(tg_id, text)

                elif event_type == "new_order_from_web":
                    beekeeper_id = payload.get("beekeeper_id")
                    if beekeeper_id:
                        text = f"🆕 Новый заказ {payload.get('order_number', '?')} из веб-панели"
                        await send_fn(beekeeper_id, text)

            except Exception as e:
                logger.warning("BotServiceClient: ошибка обработки события %s: %s", event_type, e)

        await self._bus.subscribe(STREAM_EVENTS, GROUP_BOT, handler)
        logger.info("BotServiceClient: слушает %s", STREAM_EVENTS)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _request(self, event_type: str, payload: dict, timeout: Optional[float] = None) -> dict:
        """Отправить запрос и дождаться ответа с graceful degradation."""
        event = make_event(event_type, payload)
        try:
            result = await self._bus.request_reply(
                STREAM_REQUESTS, event, timeout=timeout or self._timeout,
            )
            if isinstance(result, dict) and result.get("error"):
                logger.warning("Backend ошибка: %s → %s", event_type, result["error"])
            return result
        except TimeoutError:
            logger.warning("Backend timeout: %s (%.0fs)", event_type, timeout or self._timeout)
            return {"error": "timeout", "text": _FALLBACK_TEXT}
        except Exception as e:
            logger.warning("Backend недоступен: %s → %s", event_type, e)
            return {"error": str(e), "text": _FALLBACK_TEXT}
