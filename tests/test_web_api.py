"""Тесты FastAPI-бэкенда веб-панели управления (src/web/api.py).

Тестируемые области:
  - Аутентификация (JWT): успешный вход, неверный пароль, доступ без токена
  - Справочники: список статусов и способов доставки
  - Дашборд: агрегирование статистики через get_dashboard_stats()
  - Заказы: список, детали, смена статуса, трек-номер
  - Клиенты: список, детали с историей заказов
  - Товары: список, создание, обновление, удаление (снятие с продажи)

Все внешние вызовы CRM замокированы через unittest.mock.patch.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Устанавливаем тестовые переменные окружения ДО импорта app
os.environ.setdefault("WEB_USERNAME", "admin")
os.environ.setdefault("WEB_PASSWORD", "testpass")
os.environ.setdefault("WEB_SECRET", "test-jwt-secret")
os.environ.setdefault("INTEGRAM_URL", "http://fake-integram")
os.environ.setdefault("INTEGRAM_LOGIN", "user")
os.environ.setdefault("INTEGRAM_PASSWORD", "pass")
os.environ.setdefault("INTEGRAM_DB", "testdb")

from src.web.api import app  # noqa: E402
from src.models import Order, Client, Product, OrderItem  # noqa: E402

client = TestClient(app)


# ---------------------------------------------------------------------------
# Фикстуры: Pydantic-модели (как возвращает IntegramClient)
# ---------------------------------------------------------------------------

def _make_product(id: int = 1, name: str = "Перга", price: float = 500.0) -> Product:
    return Product(
        id=id,
        name=name,
        category="Продукты пчеловодства",
        price=price,
        weight=100,
        description="Пчелиный хлеб",
        in_stock=True,
        sku_uds="P001",
        short_name=None,
        stock=10,
    )


def _make_client(id: int = 1) -> Client:
    return Client(
        id=id,
        full_name="Иван Иванов",
        phone="+79001234567",
        telegram_id=123456,
        telegram_username="iivanov",
        address="г. Москва, ул. Пчелиная, 1",
        city="Москва",
        source="Telegram",
    )


def _make_order(id: int = 1, status: str = "Новый", total: float = 1000.0) -> Order:
    return Order(
        id=id,
        number=f"ORD-{id:04d}",
        client_id=1,
        client_name="Иван Иванов",
        date=datetime(2026, 3, 18, 12, 0, 0),
        status=status,
        delivery_method="СДЭК",
        delivery_address="Москва",
        delivery_cost=300.0,
        items_total=700.0,
        total=total,
        tracking_number=None,
        source="Telegram",
        comment=None,
        messenger=None,
        month="03.2026",
        items=[],
    )


def _make_order_item(id: int = 1, order_id: int = 1) -> OrderItem:
    return OrderItem(
        id=id,
        order_id=order_id,
        product_id=1,
        product_name="Перга",
        quantity=2,
        unit_price=350.0,
        total=700.0,
    )


def _get_token() -> str:
    """Получить валидный JWT через /api/auth/token."""
    resp = client.post(
        "/api/auth/token",
        data={"username": "admin", "password": "testpass"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers() -> dict[str, str]:
    token = _get_token()
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Вспомогательный контекст-менеджер для мока IntegramClient
# ---------------------------------------------------------------------------

def _mock_crm(**kwargs: Any):
    """Patch _get_crm() и настроить мок-клиент.

    kwargs пробрасываются как атрибуты мока:
      products=[...], orders=[...], clients=[...],
      dashboard_stats={...}, order_items=[...]
    """
    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    mock_client.authenticate = AsyncMock()

    # IntegramClient methods (возвращают Pydantic-модели)
    mock_client.get_products = AsyncMock(return_value=kwargs.get("products", []))
    mock_client.get_orders = AsyncMock(return_value=kwargs.get("orders", []))
    mock_client.get_order = AsyncMock(
        side_effect=kwargs.get("get_order_side_effect", None),
        return_value=kwargs.get("order", kwargs["orders"][0] if kwargs.get("orders") else None),
    )
    mock_client.get_clients = AsyncMock(return_value=kwargs.get("clients", []))
    mock_client.get_order_items = AsyncMock(return_value=kwargs.get("order_items", []))
    mock_client.get_dashboard_stats = AsyncMock(
        return_value=kwargs.get("dashboard_stats", {
            "total_orders": 0,
            "total_clients": 0,
            "total_revenue": 0.0,
            "avg_order": 0.0,
            "new_orders": 0,
            "delivered_orders": 0,
        }),
    )
    mock_client.get_client_telegram_id = AsyncMock(return_value=None)

    # Write operations
    mock_client.update_order_status = AsyncMock()
    mock_client.update_order = AsyncMock()
    mock_client.add_order_item = AsyncMock(return_value=kwargs.get("new_item_id", 99))
    mock_client.update_order_item = AsyncMock()
    mock_client.delete_order_item = AsyncMock()
    mock_client.recalculate_order_totals = AsyncMock()
    mock_client.create_product = AsyncMock(return_value=kwargs.get("new_product_id", 99))
    mock_client.update_product = AsyncMock()
    mock_client.delete_product = AsyncMock()
    mock_client.update_product_stock = AsyncMock()

    # Для users.py — raw API property
    mock_api = MagicMock()
    mock_api.get_all_objects = AsyncMock(return_value=[])
    mock_api.create_object = AsyncMock(return_value=99)
    mock_api.set_requisites = AsyncMock()
    mock_client.api = mock_api

    return patch("src.web.api._get_crm", new=AsyncMock(return_value=mock_client))


# ---------------------------------------------------------------------------
# Тесты: Аутентификация
# ---------------------------------------------------------------------------

class TestAuth:
    def test_login_success(self):
        resp = client.post(
            "/api/auth/token",
            data={"username": "admin", "password": "testpass"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self):
        resp = client.post(
            "/api/auth/token",
            data={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_login_wrong_username(self):
        resp = client.post(
            "/api/auth/token",
            data={"username": "hacker", "password": "testpass"},
        )
        assert resp.status_code == 401

    def test_protected_endpoint_without_token(self):
        resp = client.get("/api/dashboard")
        assert resp.status_code == 401

    def test_protected_endpoint_with_bad_token(self):
        resp = client.get(
            "/api/dashboard",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    def test_protected_endpoint_with_valid_token(self, auth_headers):
        with _mock_crm():
            resp = client.get("/api/dashboard", headers=auth_headers)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Тесты: Справочники
# ---------------------------------------------------------------------------

class TestReference:
    def test_get_reference(self, auth_headers):
        resp = client.get("/api/reference", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "order_statuses" in data
        assert "delivery_methods" in data
        assert "order_sources" in data
        assert "Новый" in data["order_statuses"]
        assert "СДЭК" in data["delivery_methods"]


# ---------------------------------------------------------------------------
# Тесты: Дашборд
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_dashboard_empty(self, auth_headers):
        with _mock_crm():
            resp = client.get("/api/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_orders"] == 0
        assert data["total_orders"] == 0
        assert data["total_revenue"] == 0.0

    def test_dashboard_with_orders(self, auth_headers):
        stats = {
            "total_orders": 2,
            "total_clients": 1,
            "total_revenue": 1500.0,
            "avg_order": 750.0,
            "new_orders": 2,
            "delivered_orders": 0,
        }
        with _mock_crm(dashboard_stats=stats):
            resp = client.get("/api/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_orders"] == 2
        assert data["total_revenue"] == pytest.approx(1500.0)

    def test_dashboard_counts_unique_clients(self, auth_headers):
        stats = {
            "total_orders": 2,
            "total_clients": 1,
            "total_revenue": 2000.0,
            "avg_order": 1000.0,
            "new_orders": 2,
            "delivered_orders": 0,
        }
        with _mock_crm(dashboard_stats=stats):
            resp = client.get("/api/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total_clients"] == 1


# ---------------------------------------------------------------------------
# Тесты: Заказы
# ---------------------------------------------------------------------------

class TestOrders:
    def test_list_orders(self, auth_headers):
        orders = [_make_order(id=1), _make_order(id=2)]
        with _mock_crm(orders=orders):
            resp = client.get("/api/orders", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_list_orders_with_status_filter(self, auth_headers):
        orders = [_make_order(status="Доставлен")]
        with _mock_crm(orders=orders):
            resp = client.get("/api/orders?status=Доставлен", headers=auth_headers)
        assert resp.status_code == 200

    def test_get_order_by_id(self, auth_headers):
        order = _make_order(id=42)
        with _mock_crm(orders=[order], order_items=[]):
            resp = client.get("/api/orders/42", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == 42

    def test_update_order_status_valid(self, auth_headers):
        order = _make_order(id=1)
        with _mock_crm(orders=[order]):
            with patch("src.web.api.notify_client_status_change", new=AsyncMock(return_value=False)):
                resp = client.patch(
                    "/api/orders/1/status",
                    json={"status": "Подтверждён"},
                    headers=auth_headers,
                )
        assert resp.status_code == 200
        assert resp.json()["status"] == "Подтверждён"

    def test_update_order_status_invalid(self, auth_headers):
        with _mock_crm():
            resp = client.patch(
                "/api/orders/1/status",
                json={"status": "НеизвестныйСтатус"},
                headers=auth_headers,
            )
        assert resp.status_code == 400

    def test_update_order_tracking(self, auth_headers):
        order = _make_order(id=1)
        with _mock_crm(orders=[order]):
            with patch("src.web.api.notify_client_tracking", new=AsyncMock(return_value=False)):
                resp = client.patch(
                    "/api/orders/1/tracking",
                    json={"tracking_number": "TRK123456"},
                    headers=auth_headers,
                )
        assert resp.status_code == 200
        assert resp.json()["tracking_number"] == "TRK123456"


# ---------------------------------------------------------------------------
# Тесты: Клиенты
# ---------------------------------------------------------------------------

class TestClients:
    def test_list_clients(self, auth_headers):
        clients_list = [_make_client(id=1), _make_client(id=2)]
        with _mock_crm(clients=clients_list):
            resp = client.get("/api/clients", headers=auth_headers)
        assert resp.status_code == 200

    def test_get_client_with_orders(self, auth_headers):
        clients_list = [_make_client(id=1)]
        orders = [_make_order(id=1)]
        with _mock_crm(clients=clients_list, orders=orders):
            resp = client.get("/api/clients/1", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "orders" in data
        assert len(data["orders"]) == 1


# ---------------------------------------------------------------------------
# Тесты: Товары
# ---------------------------------------------------------------------------

class TestProducts:
    def test_list_products(self, auth_headers):
        products = [_make_product(id=1), _make_product(id=2, name="Прополис")]
        with _mock_crm(products=products):
            resp = client.get("/api/products", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_create_product(self, auth_headers):
        with _mock_crm(new_product_id=99):
            resp = client.post(
                "/api/products",
                json={
                    "name": "Новый товар",
                    "category": "Продукты пчеловодства",
                    "price": 750.0,
                    "in_stock": True,
                },
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["product_id"] == 99

    def test_update_product(self, auth_headers):
        with _mock_crm():
            resp = client.patch(
                "/api/products/1",
                json={"price": 600.0},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_product_marks_out_of_stock(self, auth_headers):
        with _mock_crm():
            resp = client.delete("/api/products/1", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
