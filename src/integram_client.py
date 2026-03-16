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
    TABLE_ORDER_ITEMS,
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
    REQ_ORDER_MESSENGER,
    REQ_CLIENT_PHONE,
    REQ_CLIENT_TG_ID,
    REQ_CLIENT_TG_USER,
    REQ_CLIENT_ADDRESS,
    REQ_CLIENT_CITY,
    REQ_CLIENT_SOURCE,
    REQ_ITEM_QTY,
    REQ_ITEM_PRICE,
    REQ_ITEM_SUM,
    REQ_ITEM_PRODUCT,
    REQ_ITEM_ORDER,
)
from src.models import Client, Order, OrderItem, Product

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Справочники Integram (object ID → значение)
# ---------------------------------------------------------------------------

STATUS_IDS = {
    "Новый": "1086",
    "Подтверждён": "1087",
    "В сборке": "1088",
    "Отправлен": "1089",
    "Доставлен": "1090",
    "Отменён": "1091",
}

DELIVERY_IDS = {
    "СДЭК": "1092",
    "Почта России": "1093",
    "Самовывоз": "1094",
}

SOURCE_IDS = {
    "Telegram": "1082",
    "UDS": "1083",
    "WhatsApp": "1084",
    "Ручной ввод": "1085",
    "ВК": "3176",
    "Instagram": "3177",
}


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
        """Получить клиента по Telegram ID / телефону или создать нового."""
        clients = await self.get_clients()

        # Поиск по telegram_id
        if telegram_id:
            for c in clients:
                if c.telegram_id == telegram_id:
                    return c

        # Поиск по телефону
        phone = kwargs.get("phone")
        if phone:
            phone_digits = "".join(ch for ch in phone if ch.isdigit())
            for c in clients:
                if c.phone and "".join(ch for ch in c.phone if ch.isdigit()) == phone_digits:
                    return c

        # Создать нового клиента
        full_name = kwargs.get("full_name", f"Telegram {telegram_id}")
        reqs: dict[str, str] = {}
        if phone:
            reqs[REQ_CLIENT_PHONE] = phone
        if telegram_id:
            reqs[REQ_CLIENT_TG_ID] = str(telegram_id)
        if kwargs.get("telegram_username"):
            reqs[REQ_CLIENT_TG_USER] = kwargs["telegram_username"]
        if kwargs.get("address"):
            reqs[REQ_CLIENT_ADDRESS] = kwargs["address"]
        if kwargs.get("city"):
            reqs[REQ_CLIENT_CITY] = kwargs["city"]
        source = kwargs.get("source", "Telegram")
        if source in SOURCE_IDS:
            reqs[REQ_CLIENT_SOURCE] = SOURCE_IDS[source]

        obj_id = await self._api.create_object(TABLE_CLIENTS, full_name, reqs)
        logger.info("Создан клиент '%s' (id=%d) в Integram.", full_name, obj_id)

        return Client(
            id=obj_id,
            full_name=full_name,
            phone=phone,
            telegram_id=telegram_id or None,
            telegram_username=kwargs.get("telegram_username"),
            address=kwargs.get("address"),
            city=kwargs.get("city"),
            source=source,
        )

    async def update_client(self, client_id: int, **kwargs: Any) -> None:
        """Обновить данные клиента в Integram CRM."""
        field_map = {
            "full_name": None,  # val — обновляется отдельно
            "phone": REQ_CLIENT_PHONE,
            "telegram_id": REQ_CLIENT_TG_ID,
            "telegram_username": REQ_CLIENT_TG_USER,
            "address": REQ_CLIENT_ADDRESS,
            "city": REQ_CLIENT_CITY,
        }
        reqs: dict[str, str] = {}
        for py_key, req_id in field_map.items():
            if py_key in kwargs and req_id:
                reqs[req_id] = str(kwargs[py_key])
        source = kwargs.get("source")
        if source and source in SOURCE_IDS:
            reqs[REQ_CLIENT_SOURCE] = SOURCE_IDS[source]

        if reqs:
            await self._api.set_requisites(client_id, TABLE_CLIENTS, reqs)
            logger.info("Клиент %d обновлён: %s", client_id, list(kwargs.keys()))

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
        """Создать заказ в Integram CRM.

        Args:
            client_id:  ID клиента в Integram.
            items:      Список позиций [{product_id, quantity, unit_price}].
            **kwargs:   delivery_method, delivery_address, delivery_cost,
                        items_total, total, source, number, status.
        """
        # Подсчёт сумм
        items_total = kwargs.get("items_total") or sum(
            i.get("quantity", 1) * i.get("unit_price", 0) for i in items
        )
        delivery_cost = kwargs.get("delivery_cost", 0)
        total = kwargs.get("total") or (items_total + delivery_cost)
        number = kwargs.get("number", f"TG-{datetime.now().strftime('%Y%m%d-%H%M')}")
        status = kwargs.get("status", "Новый")
        source = kwargs.get("source", "Telegram")
        delivery_method = kwargs.get("delivery_method", "")

        # Собрать реквизиты
        reqs: dict[str, str] = {}
        if client_id:
            reqs[REQ_ORDER_CLIENT] = str(client_id)
        if status in STATUS_IDS:
            reqs[REQ_ORDER_STATUS] = STATUS_IDS[status]
        if delivery_method in DELIVERY_IDS:
            reqs[REQ_ORDER_DELIVERY_METHOD] = DELIVERY_IDS[delivery_method]
        if source in SOURCE_IDS:
            reqs[REQ_ORDER_SOURCE] = SOURCE_IDS[source]
        if kwargs.get("delivery_address"):
            reqs[REQ_ORDER_ADDRESS] = kwargs["delivery_address"]
        if delivery_cost:
            reqs[REQ_ORDER_DELIVERY_COST] = str(delivery_cost)
        reqs[REQ_ORDER_ITEMS_TOTAL] = str(items_total)
        reqs[REQ_ORDER_TOTAL] = str(total)
        if kwargs.get("messenger"):
            reqs[REQ_ORDER_MESSENGER] = kwargs["messenger"]

        obj_id = await self._api.create_object(TABLE_ORDERS, number, reqs)
        logger.info("Создан заказ '%s' (id=%d) в Integram. Итого: %.0f ₽", number, obj_id, total)

        # Создать позиции заказа
        for item_data in items:
            qty = item_data.get("quantity", 1)
            price = item_data.get("unit_price", 0)
            item_reqs = {
                REQ_ITEM_ORDER: str(obj_id),
                REQ_ITEM_PRODUCT: str(item_data["product_id"]),
                REQ_ITEM_QTY: str(qty),
                REQ_ITEM_PRICE: str(price),
                REQ_ITEM_SUM: str(qty * price),
            }
            item_name = f"Позиция заказа {number}"
            await self._api.create_object(TABLE_ORDER_ITEMS, item_name, item_reqs)
            logger.info(
                "Создана позиция заказа: product=%s, qty=%s, sum=%s",
                item_data["product_id"], qty, qty * price,
            )

        return Order(
            id=obj_id,
            number=number,
            client_id=client_id,
            date=datetime.now(),
            status=status,
            delivery_method=delivery_method,
            delivery_address=kwargs.get("delivery_address"),
            delivery_cost=delivery_cost,
            items_total=items_total,
            total=total,
            source=source,
            items=[],
        )

    async def update_order_status(self, order_id: int, status: str) -> None:
        """Обновить статус заказа в Integram CRM."""
        if status not in STATUS_IDS:
            logger.warning("Неизвестный статус '%s'. Допустимые: %s", status, list(STATUS_IDS.keys()))
            return
        await self._api.set_requisites(order_id, TABLE_ORDERS, {
            REQ_ORDER_STATUS: STATUS_IDS[status],
        })
        logger.info("Статус заказа %d обновлён → '%s'", order_id, status)

    # Статусы, в которых разрешено редактирование заказа
    EDITABLE_STATUSES = {"Новый", "Подтверждён", "В сборке"}

    async def update_order(self, order_id: int, **kwargs: Any) -> None:
        """Обновить поля заказа (адрес, доставка, комментарий и т.д.).

        Допустимые kwargs:
            delivery_address, delivery_method, delivery_cost,
            comment, items_total, total.
        """
        field_map = {
            "delivery_address": REQ_ORDER_ADDRESS,
            "delivery_cost": REQ_ORDER_DELIVERY_COST,
            "items_total": REQ_ORDER_ITEMS_TOTAL,
            "total": REQ_ORDER_TOTAL,
            "comment": REQ_ORDER_COMMENT,
            "tracking_number": REQ_ORDER_TRACKING,
        }
        reqs: dict[str, str] = {}
        for py_key, req_id in field_map.items():
            if py_key in kwargs:
                reqs[req_id] = str(kwargs[py_key])

        # Справочные поля (delivery_method, status, source)
        if "delivery_method" in kwargs:
            dm = kwargs["delivery_method"]
            if dm in DELIVERY_IDS:
                reqs[REQ_ORDER_DELIVERY_METHOD] = DELIVERY_IDS[dm]
        if "status" in kwargs:
            st = kwargs["status"]
            if st in STATUS_IDS:
                reqs[REQ_ORDER_STATUS] = STATUS_IDS[st]
        if "source" in kwargs:
            src = kwargs["source"]
            if src in SOURCE_IDS:
                reqs[REQ_ORDER_SOURCE] = SOURCE_IDS[src]

        if reqs:
            await self._api.set_requisites(order_id, TABLE_ORDERS, reqs)
            logger.info("Заказ %d обновлён: %s", order_id, list(kwargs.keys()))

    async def get_order_items(self, order_id: int) -> list[OrderItem]:
        """Получить позиции заказа."""
        raw = await self._api.get_order_items(order_id)
        return [
            OrderItem(
                id=item["id"],
                order_id=item["order_id"] or order_id,
                product_id=item["product_id"] or 0,
                product_name=item.get("product_name"),
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                total=item["total"],
            )
            for item in raw
        ]

    async def get_order_items_bulk(self) -> list[OrderItem]:
        """Получить ВСЕ позиции заказов (для аналитики)."""
        raw = await self._api.get_order_items(order_id=None)
        return [
            OrderItem(
                id=item["id"],
                order_id=item["order_id"] or 0,
                product_id=item["product_id"] or 0,
                product_name=item.get("product_name"),
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                total=item["total"],
            )
            for item in raw
        ]

    async def add_order_item(
        self, order_id: int, product_id: int, qty: int, price: float,
    ) -> int:
        """Добавить позицию к заказу. Возвращает ID новой позиции."""
        item_reqs = {
            REQ_ITEM_ORDER: str(order_id),
            REQ_ITEM_PRODUCT: str(product_id),
            REQ_ITEM_QTY: str(qty),
            REQ_ITEM_PRICE: str(price),
            REQ_ITEM_SUM: str(qty * price),
        }
        item_id = await self._api.create_object(
            TABLE_ORDER_ITEMS, f"Позиция заказа", item_reqs,
        )
        logger.info(
            "Добавлена позиция: order=%d, product=%d, qty=%d, sum=%.0f",
            order_id, product_id, qty, qty * price,
        )
        return item_id

    async def update_order_item(
        self, item_id: int, qty: Optional[int] = None, price: Optional[float] = None,
    ) -> None:
        """Обновить количество/цену позиции заказа."""
        reqs: dict[str, str] = {}
        if qty is not None:
            reqs[REQ_ITEM_QTY] = str(qty)
        if price is not None:
            reqs[REQ_ITEM_PRICE] = str(price)
        if qty is not None and price is not None:
            reqs[REQ_ITEM_SUM] = str(qty * price)
        elif qty is not None:
            # Нужна текущая цена для пересчёта суммы
            pass  # будет пересчитано при recalculate
        if reqs:
            await self._api.set_requisites(item_id, TABLE_ORDER_ITEMS, reqs)
            logger.info("Позиция %d обновлена: %s", item_id, reqs)

    async def delete_order_item(self, item_id: int) -> None:
        """Удалить позицию заказа."""
        await self._api.delete_object(item_id)
        logger.info("Позиция %d удалена", item_id)

    async def recalculate_order_totals(self, order_id: int) -> dict:
        """Пересчитать суммы заказа на основе позиций.

        Returns:
            {items_total, delivery_cost, total}
        """
        items = await self.get_order_items(order_id)
        items_total = sum(i.quantity * i.unit_price for i in items)

        # Получить текущую стоимость доставки
        order = await self.get_order(order_id)
        delivery_cost = order.delivery_cost or 0
        total = items_total + delivery_cost

        await self.update_order(
            order_id,
            items_total=items_total,
            total=total,
        )
        return {
            "items_total": items_total,
            "delivery_cost": delivery_cost,
            "total": total,
        }

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
