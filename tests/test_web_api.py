"""Тесты FastAPI-бэкенда веб-панели управления (src/web/api.py).

Тестируемые области:
  - Аутентификация (JWT): успешный вход, неверный пароль, доступ без токена
  - Справочники: список статусов и способов доставки
  - Дашборд: агрегирование статистики из списка заказов
  - Заказы: список, детали, смена статуса, трек-номер, ручной заказ
  - Клиенты: список, детали с историей заказов
  - Товары: список, создание, обновление, удаление (снятие с продажи)

Все внешние вызовы Integram CRM замокированы через unittest.mock.patch.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
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
from src.models import Client, Order, Product  # noqa: E402

client = TestClient(app)


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

def _make_product(id: int = 1, name: str = "Перга", price: float = 500.0) -> Product:
    return Product.model_validate({
        "id": id,
        "Название": name,
        "Категория": "Продукты пчеловодства",
        "Цена": price,
        "Вес": 100,
        "Описание": "Пчелиный хлеб",
        "В наличии": True,
        "Артикул UDS": "P001",
    })


def _make_client(id: int = 1) -> Client:
    return Client.model_validate({
        "id": id,
        "ФИО": "Иван Иванов",
        "Телефон": "+79001234567",
        "Telegram ID": 123456,
        "Telegram Username": "iivanov",
        "Адрес": "г. Москва, ул. Пчелиная, 1",
        "Город": "Москва",
        "Источник": "Telegram",
    })


def _make_order(id: int = 1, status: str = "Новый", total: float = 1000.0) -> Order:
    return Order.model_validate({
        "id": id,
        "Номер": f"ORD-{id:04d}",
        "client_id": 1,
        "client_name": "Иван Иванов",
        "Дата": datetime.now(timezone.utc).isoformat(),
        "Статус": status,
        "Способ доставки": "СДЭК",
        "Адрес доставки": "Москва",
        "Стоимость доставки": 300.0,
        "Сумма товаров": 700.0,
        "Итого": total,
        "Трек-номер": None,
        "Источник": "Telegram",
        "items": [],
    })


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

def _mock_integram(**kwargs: Any):
    """Patch _get_integram() и настроить мок-клиент.

    kwargs пробрасываются как атрибуты мока:
      products=[...], orders=[...], clients=[...], raw_client={...}
    """
    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    mock_client.authenticate = AsyncMock()

    if "products" in kwargs:
        mock_client.get_products = AsyncMock(return_value=kwargs["products"])
    if "orders" in kwargs:
        mock_client.get_orders = AsyncMock(return_value=kwargs["orders"])
    if "order" in kwargs:
        mock_client.get_order = AsyncMock(return_value=kwargs["order"])
    if "create_order_result" in kwargs:
        mock_client.create_order = AsyncMock(return_value=kwargs["create_order_result"])
    if "update_order_status" in kwargs:
        mock_client.update_order_status = AsyncMock(return_value=kwargs["update_order_status"])
    else:
        mock_client.update_order_status = AsyncMock()
    if "raw_client" in kwargs:
        mock_client._request = AsyncMock(return_value=kwargs["raw_client"])
    if "raw_clients_list" in kwargs:
        mock_client._request = AsyncMock(return_value=kwargs["raw_clients_list"])
    mock_client._parse_client = MagicMock(side_effect=lambda d: _make_client())
    mock_client._parse_product = MagicMock(side_effect=lambda d: _make_product())

    return patch("src.web.api._get_integram", new=AsyncMock(return_value=mock_client))


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
        orders = [_make_order()]
        with _mock_integram(orders=orders):
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
        assert "Новый" in data["order_statuses"]
        assert "СДЭК" in data["delivery_methods"]


# ---------------------------------------------------------------------------
# Тесты: Дашборд
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_dashboard_empty(self, auth_headers):
        with _mock_integram(orders=[]):
            resp = client.get("/api/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_orders_today"] == 0
        assert data["total_orders"] == 0
        assert data["revenue_today"] == 0.0

    def test_dashboard_with_orders(self, auth_headers):
        orders = [_make_order(id=1, total=1000.0), _make_order(id=2, total=500.0)]
        with _mock_integram(orders=orders):
            resp = client.get("/api/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_orders"] == 2
        assert data["revenue_today"] == pytest.approx(1500.0)

    def test_dashboard_counts_unique_clients(self, auth_headers):
        o1 = _make_order(id=1)
        o2 = _make_order(id=2)
        # Оба от одного клиента (client_id=1)
        with _mock_integram(orders=[o1, o2]):
            resp = client.get("/api/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total_clients"] == 1


# ---------------------------------------------------------------------------
# Тесты: Заказы
# ---------------------------------------------------------------------------

class TestOrders:
    def test_list_orders(self, auth_headers):
        orders = [_make_order(id=1), _make_order(id=2)]
        with _mock_integram(orders=orders):
            resp = client.get("/api/orders", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_orders_with_status_filter(self, auth_headers):
        orders = [_make_order(status="Доставлен")]
        with _mock_integram(orders=orders):
            resp = client.get("/api/orders?status=Доставлен", headers=auth_headers)
        assert resp.status_code == 200

    def test_get_order_by_id(self, auth_headers):
        order = _make_order(id=42)
        with _mock_integram(order=order):
            resp = client.get("/api/orders/42", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == 42

    def test_update_order_status_valid(self, auth_headers):
        with _mock_integram():
            resp = client.patch(
                "/api/orders/1/status",
                json={"status": "Подтверждён"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "Подтверждён"

    def test_update_order_status_invalid(self, auth_headers):
        resp = client.patch(
            "/api/orders/1/status",
            json={"status": "НеизвестныйСтатус"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_update_order_tracking(self, auth_headers):
        raw_order = {"id": 1, "Номер": "ORD-0001", "Трек-номер": "TRK123"}
        with _mock_integram(raw_client=raw_order):
            resp = client.patch(
                "/api/orders/1/tracking",
                json={"tracking_number": "TRK123456"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["tracking_number"] == "TRK123456"

    def test_create_manual_order(self, auth_headers):
        raw_client_resp = {"id": 99}
        created_order = _make_order(id=10)

        mock_integram = MagicMock()
        mock_integram.close = AsyncMock()
        mock_integram._request = AsyncMock(return_value=raw_client_resp)
        mock_integram.create_order = AsyncMock(return_value=created_order)

        with patch("src.web.api._get_integram", new=AsyncMock(return_value=mock_integram)):
            resp = client.post(
                "/api/orders",
                json={
                    "client_name": "Мария Петрова",
                    "phone": "+79009998877",
                    "delivery_method": "СДЭК",
                    "delivery_address": "Москва, Пчелиная 1",
                    "delivery_cost": 300.0,
                    "items": [
                        {"product_id": 1, "quantity": 2, "unit_price": 500.0}
                    ],
                },
                headers=auth_headers,
            )
        assert resp.status_code == 201

    def test_create_manual_order_invalid_delivery(self, auth_headers):
        resp = client.post(
            "/api/orders",
            json={
                "client_name": "Иван",
                "delivery_method": "Самолёт",  # не существует
                "items": [{"product_id": 1, "quantity": 1, "unit_price": 100.0}],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Тесты: Клиенты
# ---------------------------------------------------------------------------

class TestClients:
    def test_list_clients(self, auth_headers):
        raw_list = [
            {"id": 1, "ФИО": "Иван Иванов"},
            {"id": 2, "ФИО": "Мария Петрова"},
        ]
        with _mock_integram(raw_clients_list=raw_list):
            resp = client.get("/api/clients", headers=auth_headers)
        assert resp.status_code == 200

    def test_get_client_with_orders(self, auth_headers):
        raw_client_data = {"id": 1, "ФИО": "Иван Иванов"}
        orders = [_make_order()]

        mock_integram = MagicMock()
        mock_integram.close = AsyncMock()
        mock_integram._request = AsyncMock(return_value=raw_client_data)
        mock_integram._parse_client = MagicMock(return_value=_make_client())
        mock_integram.get_orders = AsyncMock(return_value=orders)

        with patch("src.web.api._get_integram", new=AsyncMock(return_value=mock_integram)):
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
        with _mock_integram(products=products):
            resp = client.get("/api/products", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_create_product(self, auth_headers):
        raw_response = {
            "id": 99,
            "Название": "Новый товар",
            "В наличии": True,
        }
        mock_integram = MagicMock()
        mock_integram.close = AsyncMock()
        mock_integram._request = AsyncMock(return_value=raw_response)
        mock_integram._parse_product = MagicMock(return_value=_make_product(id=99, name="Новый товар"))

        with patch("src.web.api._get_integram", new=AsyncMock(return_value=mock_integram)):
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
        assert resp.status_code == 201

    def test_update_product(self, auth_headers):
        raw_response = {"id": 1, "Название": "Перга (обновлена)", "В наличии": True}
        mock_integram = MagicMock()
        mock_integram.close = AsyncMock()
        mock_integram._request = AsyncMock(return_value=raw_response)
        mock_integram._parse_product = MagicMock(return_value=_make_product())

        with patch("src.web.api._get_integram", new=AsyncMock(return_value=mock_integram)):
            resp = client.patch(
                "/api/products/1",
                json={"price": 600.0},
                headers=auth_headers,
            )
        assert resp.status_code == 200

    def test_delete_product_marks_out_of_stock(self, auth_headers):
        raw_response = {"id": 1, "В наличии": False}
        mock_integram = MagicMock()
        mock_integram.close = AsyncMock()
        mock_integram._request = AsyncMock(return_value=raw_response)

        with patch("src.web.api._get_integram", new=AsyncMock(return_value=mock_integram)):
            resp = client.delete("/api/products/1", headers=auth_headers)
        assert resp.status_code == 200

        # Проверяем, что отправлен PATCH с {"В наличии": False}
        call_kwargs = mock_integram._request.call_args
        assert call_kwargs.kwargs["json"]["В наличии"] is False
