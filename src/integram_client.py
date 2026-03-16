"""Python-клиент для Integram CRM (ai2o.ru).

Обёртка над IntegramAPI (реальный HTTP-клиент) для runtime-кода бота.
Возвращает типизированные Pydantic-модели (Product, Client, Order).

Конфигурация через .env:
  INTEGRAM_URL      — базовый URL (https://ai2o.ru)
  INTEGRAM_LOGIN    — логин
  INTEGRAM_PASSWORD — пароль
  INTEGRAM_DB       — имя базы (bibot)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from src.integram_api import (
    IntegramAPI,
    IntegramAPIError,
    TABLE_ORDERS,
    TABLE_CLIENTS,
    TABLE_PRODUCTS,
    REQ_ORDER_DATE,
    REQ_ORDER_ADDRESS,
    REQ_ORDER_DELIVERY_COST,
    REQ_ORDER_ITEMS_TOTAL,
    REQ_ORDER_TOTAL,
    REQ_ORDER_TRACKING,
    REQ_ORDER_COMMENT,
    REQ_ORDER_CLIENT,
    REQ_ORDER_STATUS,
    REQ_ORDER_DELIVERY_METHOD,
    REQ_ORDER_SOURCE,
    REQ_CLIENT_PHONE,
    REQ_CLIENT_TG_ID,
    REQ_CLIENT_TG_USER,
    REQ_CLIENT_ADDRESS,
    REQ_CLIENT_CITY,
    REQ_CLIENT_SOURCE,
    REQ_PRODUCT_PRICE,
    REQ_PRODUCT_WEIGHT,
    REQ_PRODUCT_DESC,
    REQ_PRODUCT_INSTOCK,
    REQ_PRODUCT_SKU,
    REQ_PRODUCT_CATEGORY,
    _strip_html,
    _extract_ref_text,
    _extract_ref_id,
    _parse_number,
)
from src.models import Client, Order, OrderItem, Product

logger = logging.getLogger(__name__)


class IntegramError(Exception):
    """Базовое исключение клиента Integram."""


class IntegramAuthError(IntegramError):
    """Ошибка аутентификации."""


class IntegramNotFoundError(IntegramError):
    """Запись не найдена."""


class IntegramClient:
    """Async-клиент для работы с Integram CRM.

    Делегирует HTTP-вызовы в IntegramAPI, возвращает Pydantic-модели.

    Использование::

        client = IntegramClient()
        await client.authenticate()
        products = await client.get_products()
    """

    def __init__(self, **kwargs: Any) -> None:
        self._api = IntegramAPI()
        self._authenticated = False

    async def authenticate(self) -> None:
        """Авторизация в Integram CRM."""
        try:
            await self._api.authenticate()
            self._authenticated = True
            logger.info("Аутентификация в Integram прошла успешно.")
        except IntegramAPIError as e:
            raise IntegramAuthError(str(e)) from e

    async def close(self) -> None:
        """Закрыть HTTP-сессию."""
        await self._api.close()

    async def __aenter__(self) -> "IntegramClient":
        await self.authenticate()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Товары
    # ------------------------------------------------------------------

    async def get_products(self, in_stock_only: bool = True) -> list[Product]:
        """Получить список товаров."""
        raw = await self._api.get_products()
        products = []
        for item in raw:
            product = Product(
                id=item["id"],
                name=item["name"],
                category=item.get("category"),
                price=item.get("price"),
                weight=item.get("weight"),
                description=item.get("description"),
                in_stock=item.get("in_stock", True),
                sku_uds=item.get("sku_uds"),
            )
            if in_stock_only and not product.in_stock:
                continue
            products.append(product)
        return products

    async def get_product_by_name(self, name: str) -> Optional[Product]:
        """Найти товар по названию."""
        products = await self.get_products(in_stock_only=False)
        name_lower = name.lower()
        for product in products:
            if product.name.lower() == name_lower:
                return product
        return None

    # ------------------------------------------------------------------
    # Клиенты
    # ------------------------------------------------------------------

    async def get_clients(self) -> list[Client]:
        """Получить всех клиентов."""
        raw = await self._api.get_clients()
        return [
            Client(
                id=c["id"],
                full_name=c["name"],
                phone=c.get("phone") or None,
                telegram_id=int(c["telegram_id"]) if c.get("telegram_id") else None,
                telegram_username=c.get("telegram_username") or None,
                address=c.get("address") or None,
                city=c.get("city") or None,
                source=c.get("source") or None,
            )
            for c in raw
        ]

    async def get_or_create_client(
        self,
        telegram_id: int,
        **kwargs: Any,
    ) -> Client:
        """Получить клиента по Telegram ID или создать нового."""
        clients = await self.get_clients()

        # Поиск по telegram_id
        if telegram_id:
            for c in clients:
                if c.telegram_id == telegram_id:
                    return c

        # Поиск по телефону
        phone = kwargs.get("phone")
        if phone:
            phone_digits = "".join(c for c in phone if c.isdigit())
            for c in clients:
                if c.phone and "".join(ch for ch in c.phone if ch.isdigit()) == phone_digits:
                    return c

        # Клиент не найден — создание пока не реализовано через API
        # Возвращаем заглушку с переданными данными
        logger.warning(
            "Клиент telegram_id=%s не найден в CRM. "
            "Создание через API пока не реализовано.",
            telegram_id,
        )
        return Client(
            id=0,
            full_name=kwargs.get("full_name", f"Telegram {telegram_id}"),
            phone=kwargs.get("phone"),
            telegram_id=telegram_id or None,
            telegram_username=kwargs.get("telegram_username"),
            address=kwargs.get("address"),
            city=kwargs.get("city"),
            source=kwargs.get("source"),
        )

    async def update_client(self, client_id: int, **kwargs: Any) -> None:
        """Обновить данные клиента (пока заглушка — логирует)."""
        logger.info("update_client(%d, %s) — запись через API пока не реализована.", client_id, kwargs)

    # ------------------------------------------------------------------
    # Заказы
    # ------------------------------------------------------------------

    async def get_orders(
        self,
        client_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> list[Order]:
        """Получить список заказов с фильтрацией."""
        raw = await self._api.get_orders()
        orders = []
        for item in raw:
            order = self._dict_to_order(item)
            if client_id is not None and order.client_id != client_id:
                continue
            if status is not None and order.status != status:
                continue
            orders.append(order)
        return orders

    async def get_order(self, order_id: int) -> Order:
        """Получить заказ по ID."""
        raw = await self._api.get_orders()
        for item in raw:
            if item["id"] == order_id:
                return self._dict_to_order(item)
        raise IntegramNotFoundError(f"Заказ {order_id} не найден.")

    async def create_order(
        self,
        client_id: int,
        items: list[dict],
        **kwargs: Any,
    ) -> Order:
        """Создать заказ (пока заглушка — логирует и возвращает объект)."""
        logger.info(
            "create_order(client=%d, items=%d, %s) — запись через API пока не реализована.",
            client_id, len(items), kwargs,
        )
        return Order(
            id=0,
            number=kwargs.get("number", "NEW"),
            client_id=client_id,
            date=datetime.now(),
            status=kwargs.get("status", "Новый"),
            total=kwargs.get("total"),
            source=kwargs.get("source"),
            items=[],
        )

    async def update_order_status(self, order_id: int, status: str) -> None:
        """Обновить статус заказа (пока заглушка — логирует)."""
        logger.info(
            "update_order_status(%d, '%s') — запись через API пока не реализована.",
            order_id, status,
        )

    async def add_order_item(self, order_id: int, product_id: int, qty: int) -> None:
        """Добавить позицию к заказу (пока заглушка)."""
        logger.info(
            "add_order_item(%d, product=%d, qty=%d) — не реализовано.",
            order_id, product_id, qty,
        )

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    @staticmethod
    def _dict_to_order(item: dict) -> Order:
        """Конвертировать dict из IntegramAPI.get_orders() в Order."""
        date_str = item.get("date", "")
        try:
            if "." in date_str:
                parts = date_str.split()
                day, month, year = parts[0].split(".")
                date = datetime(int(year), int(month), int(day))
            else:
                date = datetime.fromisoformat(date_str) if date_str else datetime.now()
        except (ValueError, IndexError):
            date = datetime.now()

        return Order(
            id=item.get("id", 0),
            number=item.get("number", ""),
            client_id=item.get("client_id") or 0,
            client_name=item.get("client_name"),
            date=date,
            status=item.get("status", ""),
            delivery_method=item.get("delivery_method"),
            delivery_address=item.get("delivery_address"),
            delivery_cost=item.get("delivery_cost"),
            items_total=item.get("items_total"),
            total=item.get("total"),
            tracking_number=item.get("tracking_number"),
            source=item.get("source"),
            items=[],
        )
