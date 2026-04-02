"""Тесты BusHandlers — маршрутизация событий из шины → сервисы."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.web.bus_handlers import BusHandlers
from src.bus import EventBus, make_event
from src.models import Order, OrderItem

pytestmark = pytest.mark.asyncio


def _make_order(**kw) -> Order:
    defaults = dict(
        id=100, number="TG-001", client_id=10, client_name="Иван",
        date=datetime(2026, 4, 1), status="Новый",
        delivery_method=None, delivery_address=None,
        delivery_cost=0, items_total=2800, total=2800,
        tracking_number=None, source="Telegram", comment=None,
        messenger=None, month=None, batch_id=None, items=[],
    )
    defaults.update(kw)
    return Order(**defaults)


def _make_bus():
    bus = AsyncMock(spec=EventBus)
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


def _make_order_svc():
    svc = AsyncMock()
    svc.create_order = AsyncMock(return_value=_make_order())
    svc.update_status = AsyncMock(return_value=_make_order(status="Подтверждён"))
    svc.get_orders = AsyncMock(return_value=[_make_order()])
    svc.get_order = AsyncMock(return_value=_make_order())
    svc.get_order_items = AsyncMock(return_value=[])
    return svc


# ------------------------------------------------------------------
# Dispatch
# ------------------------------------------------------------------

async def test_dispatch_ping():
    bus = _make_bus()
    h = BusHandlers(bus)
    result = await h._dispatch({"type": "ping", "payload": {}})
    assert result == {"pong": True}


async def test_dispatch_unknown():
    bus = _make_bus()
    h = BusHandlers(bus)
    result = await h._dispatch({"type": "unknown_type", "payload": {}})
    assert "error" in result


# ------------------------------------------------------------------
# Order handlers
# ------------------------------------------------------------------

async def test_create_order():
    bus = _make_bus()
    order_svc = _make_order_svc()
    h = BusHandlers(bus, order_service=order_svc)

    result = await h._dispatch({
        "type": "create_order",
        "payload": {
            "client_id": 10,
            "items": [{"product_id": 1, "quantity": 2, "unit_price": 1400}],
            "source": "Telegram",
        },
    })

    assert result["order_id"] == 100
    assert result["order_number"] == "TG-001"
    order_svc.create_order.assert_called_once()


async def test_update_status():
    bus = _make_bus()
    order_svc = _make_order_svc()
    h = BusHandlers(bus, order_service=order_svc)

    result = await h._dispatch({
        "type": "update_order_status",
        "payload": {"order_id": 100, "status": "Подтверждён"},
    })

    assert result["status"] == "Подтверждён"
    order_svc.update_status.assert_called_once()


async def test_get_orders():
    bus = _make_bus()
    order_svc = _make_order_svc()
    h = BusHandlers(bus, order_service=order_svc)

    result = await h._dispatch({
        "type": "get_orders",
        "payload": {"status": "Новый"},
    })

    assert len(result["orders"]) == 1
    order_svc.get_orders.assert_called_once()


async def test_get_order():
    bus = _make_bus()
    order_svc = _make_order_svc()
    h = BusHandlers(bus, order_service=order_svc)

    result = await h._dispatch({
        "type": "get_order",
        "payload": {"order_id": 100},
    })

    assert result["id"] == 100
    assert result["number"] == "TG-001"


async def test_no_service_returns_error():
    bus = _make_bus()
    h = BusHandlers(bus)  # без order_service

    result = await h._dispatch({
        "type": "create_order",
        "payload": {"client_id": 10, "items": []},
    })

    assert "error" in result


# ------------------------------------------------------------------
# Events (Backend → Bot)
# ------------------------------------------------------------------

async def test_publish_event():
    bus = _make_bus()
    h = BusHandlers(bus)

    await h.publish_event("order_status_changed", {"order_id": 100, "status": "Доставлен"})

    bus.publish.assert_called_once()
    call_args = bus.publish.call_args
    assert call_args[0][0] == "stream:events"


# ------------------------------------------------------------------
# Start
# ------------------------------------------------------------------

async def test_start_subscribes():
    bus = _make_bus()
    h = BusHandlers(bus)

    await h.start()

    bus.subscribe.assert_called_once_with(
        "stream:requests", "backend", h._dispatch,
    )
