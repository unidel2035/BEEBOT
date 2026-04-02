"""Тесты EventBus — publish/subscribe/request_reply.

Требует запущенный Redis (docker compose up redis).
Пропускается если Redis недоступен.
"""

import asyncio
import json
import time

import pytest
import pytest_asyncio

try:
    import redis.asyncio as aioredis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

from src.bus import EventBus, make_event

pytestmark = pytest.mark.asyncio

REDIS_URL = "redis://localhost:6379/15"  # тестовая БД 15


async def _redis_available() -> bool:
    """Проверить доступность Redis."""
    if not HAS_REDIS:
        return False
    try:
        r = aioredis.from_url(REDIS_URL, socket_connect_timeout=1)
        await r.ping()
        await r.aclose()
        return True
    except Exception:
        return False


skip_no_redis = pytest.mark.skipif(
    not HAS_REDIS,
    reason="redis package not installed",
)


@pytest_asyncio.fixture
async def bus():
    """EventBus подключённый к тестовой БД."""
    available = await _redis_available()
    if not available:
        pytest.skip("Redis недоступен")
    b = EventBus(REDIS_URL)
    await b.connect()
    # Очистить тестовую БД
    await b._redis.flushdb()
    yield b
    await b.close()


# ------------------------------------------------------------------
# make_event
# ------------------------------------------------------------------

def test_make_event_basic():
    """make_event создаёт корректную структуру."""
    event = make_event("consult", {"query": "что такое прополис"})
    assert event["type"] == "consult"
    assert event["payload"]["query"] == "что такое прополис"
    assert event["timestamp"] > 0
    assert event["reply_to"] == ""
    assert event["correlation_id"] == ""


def test_make_event_with_reply():
    """make_event с reply_to и correlation_id."""
    event = make_event(
        "consult",
        {"query": "test"},
        reply_to="replies:abc",
        correlation_id="abc",
    )
    assert event["reply_to"] == "replies:abc"
    assert event["correlation_id"] == "abc"


# ------------------------------------------------------------------
# Publish
# ------------------------------------------------------------------

@skip_no_redis
async def test_publish(bus: EventBus):
    """publish отправляет событие в stream."""
    event = make_event("test", {"value": 42})
    msg_id = await bus.publish("test:stream", event)
    assert msg_id

    # Проверить что событие в stream
    messages = await bus._redis.xrange("test:stream")
    assert len(messages) == 1
    data = json.loads(messages[0][1]["data"])
    assert data["type"] == "test"
    assert data["payload"]["value"] == 42


# ------------------------------------------------------------------
# Subscribe
# ------------------------------------------------------------------

@skip_no_redis
async def test_subscribe(bus: EventBus):
    """subscribe получает события из stream."""
    received = []

    async def handler(event):
        received.append(event)
        return None

    await bus.subscribe("test:sub", "test-group", handler)

    # Отправить событие
    event = make_event("greeting", {"name": "пчеловод"})
    await bus.publish("test:sub", event)

    # Подождать обработки
    for _ in range(20):
        if received:
            break
        await asyncio.sleep(0.1)

    assert len(received) == 1
    assert received[0]["type"] == "greeting"
    assert received[0]["payload"]["name"] == "пчеловод"


@skip_no_redis
async def test_subscribe_multiple(bus: EventBus):
    """subscribe обрабатывает несколько событий."""
    received = []

    async def handler(event):
        received.append(event["type"])
        return None

    await bus.subscribe("test:multi", "test-group", handler)

    for i in range(5):
        await bus.publish("test:multi", make_event(f"event-{i}"))

    for _ in range(30):
        if len(received) >= 5:
            break
        await asyncio.sleep(0.1)

    assert len(received) == 5


# ------------------------------------------------------------------
# Request-Reply
# ------------------------------------------------------------------

@skip_no_redis
async def test_request_reply(bus: EventBus):
    """request_reply получает ответ от handler."""

    async def handler(event):
        if event["type"] == "question":
            return {"answer": f"ответ на {event['payload']['q']}"}
        return None

    await bus.subscribe("test:rr", "rr-group", handler)

    event = make_event("question", {"q": "прополис"})
    result = await bus.request_reply("test:rr", event, timeout=5)

    assert result["answer"] == "ответ на прополис"


@skip_no_redis
async def test_request_reply_timeout(bus: EventBus):
    """request_reply бросает TimeoutError если нет ответа."""
    event = make_event("nobody_listens", {"q": "hello"})

    with pytest.raises(TimeoutError):
        await bus.request_reply("test:empty", event, timeout=0.5)


# ------------------------------------------------------------------
# Connection
# ------------------------------------------------------------------

@skip_no_redis
async def test_connect_disconnect(bus: EventBus):
    """connect/close работают корректно."""
    assert bus.connected
    await bus.close()
    assert not bus.connected


def test_make_event_without_redis():
    """make_event работает без подключения к Redis."""
    event = make_event("offline", {"status": "ok"})
    assert event["type"] == "offline"
