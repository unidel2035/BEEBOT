"""Тесты OrderService — единый источник правды для заказов."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from src.services.order_service import OrderService, EDITABLE_STATUSES
from src.services.notification_service import NotificationService
from src.models import Order, OrderItem

pytestmark = pytest.mark.asyncio


def _make_order(**overrides) -> Order:
    from datetime import datetime
    defaults = dict(
        id=100, number="TG-20260401-1200", client_id=10,
        client_name="Иван", date=datetime(2026, 4, 1), status="Новый",
        delivery_method="СДЭК", delivery_address="Москва",
        delivery_cost=350, items_total=2800, total=3150,
        tracking_number=None, source="Telegram", comment=None,
        messenger=None, month=None, batch_id=None, items=[],
    )
    defaults.update(overrides)
    return Order(**defaults)


def _make_crm():
    crm = AsyncMock()
    crm.create_order = AsyncMock(return_value=_make_order())
    crm.get_order = AsyncMock(return_value=_make_order())
    crm.get_orders = AsyncMock(return_value=[_make_order()])
    crm.get_order_items = AsyncMock(return_value=[])
    crm.get_order_items_bulk = AsyncMock(return_value=[])
    crm.get_or_create_client = AsyncMock(return_value=MagicMock(id=10))
    crm.update_client = AsyncMock()
    crm.update_order_status = AsyncMock()
    crm.update_order = AsyncMock()
    crm.add_order_item = AsyncMock(return_value=200)
    crm.update_order_item = AsyncMock()
    crm.delete_order_item = AsyncMock()
    crm.recalculate_order_totals = AsyncMock(return_value={"items_total": 2800, "total": 3150})
    return crm


def _make_notifier():
    n = AsyncMock(spec=NotificationService)
    return n


# ------------------------------------------------------------------
# Создание заказа
# ------------------------------------------------------------------

async def test_create_order_basic():
    crm = _make_crm()
    svc = OrderService(crm)

    order = await svc.create_order(
        client_id=10,
        items=[{"product_id": 1, "quantity": 2, "unit_price": 1400}],
        source="Telegram",
    )

    crm.create_order.assert_called_once()
    call_kwargs = crm.create_order.call_args
    assert call_kwargs.kwargs["client_id"] == 10
    assert call_kwargs.kwargs["items_total"] == 2800
    assert call_kwargs.kwargs["total"] == 2800  # без доставки


async def test_create_order_with_delivery():
    crm = _make_crm()
    svc = OrderService(crm)

    await svc.create_order(
        client_id=10,
        items=[{"product_id": 1, "quantity": 1, "unit_price": 1000}],
        delivery_cost=350,
    )

    call_kwargs = crm.create_order.call_args
    assert call_kwargs.kwargs["total"] == 1350


async def test_create_order_sends_notification():
    crm = _make_crm()
    notifier = _make_notifier()
    svc = OrderService(crm, notifier)

    await svc.create_order(
        client_id=10,
        items=[{"product_id": 1, "quantity": 1, "unit_price": 1000}],
    )

    notifier.on_order_created.assert_called_once()


async def test_create_order_with_client():
    crm = _make_crm()
    svc = OrderService(crm)

    await svc.create_order_with_client(
        telegram_id=123,
        full_name="Иван Петров",
        phone="+79001234567",
        items=[{"product_id": 1, "quantity": 1, "unit_price": 1400}],
        address="Москва",
    )

    crm.get_or_create_client.assert_called_once()
    crm.update_client.assert_called_once()
    crm.create_order.assert_called_once()


# ------------------------------------------------------------------
# Статус
# ------------------------------------------------------------------

async def test_update_status_valid():
    crm = _make_crm()
    notifier = _make_notifier()
    svc = OrderService(crm, notifier)

    await svc.update_status(100, "Подтверждён")

    crm.update_order_status.assert_called_once_with(
        100, "Подтверждён", from_status="Новый", comment="",
    )
    notifier.on_status_changed.assert_called_once()


async def test_update_status_invalid():
    crm = _make_crm()
    svc = OrderService(crm)

    with pytest.raises(ValueError, match="Некорректный статус"):
        await svc.update_status(100, "Несуществующий")


async def test_update_status_warehouse_allowed():
    crm = _make_crm()
    crm.get_order = AsyncMock(return_value=_make_order(status="Подтверждён"))
    svc = OrderService(crm)

    await svc.update_status(100, "В сборке", role="warehouse")
    crm.update_order_status.assert_called_once()


async def test_update_status_warehouse_denied():
    crm = _make_crm()
    crm.get_order = AsyncMock(return_value=_make_order(status="Новый"))
    svc = OrderService(crm)

    with pytest.raises(PermissionError):
        await svc.update_status(100, "Доставлен", role="warehouse")


# ------------------------------------------------------------------
# Позиции
# ------------------------------------------------------------------

async def test_add_item():
    crm = _make_crm()
    svc = OrderService(crm)

    item_id = await svc.add_item(100, product_id=5, quantity=2, unit_price=600)

    assert item_id == 200
    crm.add_order_item.assert_called_once_with(100, 5, 2, 600)
    crm.recalculate_order_totals.assert_called_once_with(100)


async def test_add_item_not_editable():
    crm = _make_crm()
    crm.get_order = AsyncMock(return_value=_make_order(status="Отправлен"))
    svc = OrderService(crm)

    with pytest.raises(ValueError, match="нельзя редактировать"):
        await svc.add_item(100, product_id=5, quantity=1, unit_price=600)


async def test_delete_item():
    crm = _make_crm()
    svc = OrderService(crm)

    await svc.delete_item(100, item_id=200)

    crm.delete_order_item.assert_called_once_with(200)
    crm.recalculate_order_totals.assert_called_once_with(100)


# ------------------------------------------------------------------
# Обновление полей
# ------------------------------------------------------------------

async def test_update_order_tracking_notifies():
    crm = _make_crm()
    notifier = _make_notifier()
    svc = OrderService(crm, notifier)

    await svc.update_order(100, tracking_number="CDEK-123")

    crm.update_order.assert_called_once()
    notifier.on_tracking_added.assert_called_once()


async def test_update_order_address():
    crm = _make_crm()
    svc = OrderService(crm)

    await svc.update_order(100, delivery_address="Санкт-Петербург")

    crm.update_order.assert_called_once_with(100, delivery_address="Санкт-Петербург")


# ------------------------------------------------------------------
# Чтение
# ------------------------------------------------------------------

async def test_get_orders():
    crm = _make_crm()
    svc = OrderService(crm)

    orders = await svc.get_orders(status="Новый")

    crm.get_orders.assert_called_once_with(client_id=None, status="Новый")
    assert len(orders) == 1
