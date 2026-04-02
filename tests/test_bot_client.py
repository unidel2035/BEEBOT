"""Тесты BotServiceClient — клиент бота для обращения к Backend."""

import pytest
from unittest.mock import AsyncMock

from src.bot_client import BotServiceClient
from src.bus import EventBus

pytestmark = pytest.mark.asyncio


def _make_bus():
    bus = AsyncMock(spec=EventBus)
    bus.request_reply = AsyncMock(return_value={"text": "Прополис — природный антибиотик."})
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


async def test_consult():
    bus = _make_bus()
    client = BotServiceClient(bus)

    result = await client.consult(user_id=123, query="что такое прополис")

    bus.request_reply.assert_called_once()
    event = bus.request_reply.call_args[0][1]
    assert event["type"] == "consult"
    assert event["payload"]["query"] == "что такое прополис"
    assert result["text"] == "Прополис — природный антибиотик."


async def test_create_order():
    bus = _make_bus()
    bus.request_reply = AsyncMock(return_value={"order_id": 100, "order_number": "TG-001"})
    client = BotServiceClient(bus)

    result = await client.create_order(
        client_id=10,
        items=[{"product_id": 1, "quantity": 2, "unit_price": 1400}],
        source="Telegram",
    )

    assert result["order_id"] == 100
    event = bus.request_reply.call_args[0][1]
    assert event["type"] == "create_order"


async def test_update_status():
    bus = _make_bus()
    bus.request_reply = AsyncMock(return_value={"order_id": 100, "status": "Подтверждён"})
    client = BotServiceClient(bus)

    result = await client.update_order_status(100, "Подтверждён")

    assert result["status"] == "Подтверждён"


async def test_get_orders():
    bus = _make_bus()
    bus.request_reply = AsyncMock(return_value={"orders": [{"id": 1}]})
    client = BotServiceClient(bus)

    result = await client.get_orders(status="Новый")

    assert len(result["orders"]) == 1


async def test_ping():
    bus = _make_bus()
    bus.request_reply = AsyncMock(return_value={"pong": True})
    client = BotServiceClient(bus)

    result = await client.ping()

    assert result["pong"] is True
    # ping uses 5s timeout
    call_kwargs = bus.request_reply.call_args
    assert call_kwargs.kwargs.get("timeout") == 5.0 or call_kwargs[0][2] == 5.0


async def test_timeout_graceful():
    bus = _make_bus()
    bus.request_reply = AsyncMock(side_effect=TimeoutError("timeout"))
    client = BotServiceClient(bus, timeout=1.0)

    result = await client.consult(user_id=123, query="test")

    assert result["error"] == "timeout"
    assert "недоступен" in result["text"]


async def test_connection_error_graceful():
    bus = _make_bus()
    bus.request_reply = AsyncMock(side_effect=ConnectionError("redis down"))
    client = BotServiceClient(bus)

    result = await client.consult(user_id=123, query="test")

    assert "error" in result
    assert "text" in result


async def test_listen_events():
    bus = _make_bus()
    client = BotServiceClient(bus)

    send_fn = AsyncMock()
    await client.listen_events(send_fn)

    bus.subscribe.assert_called_once()
    assert bus.subscribe.call_args[0][0] == "stream:events"
    assert bus.subscribe.call_args[0][1] == "bot"
