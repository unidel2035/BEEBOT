"""Клиент для реального HTTP API Integram (ai2o.ru).

Integram использует собственный REST-подобный API:
  POST /{db}/auth?JSON              — авторизация (login, pwd)
  GET  /{db}/object/{table_id}?JSON — получить записи таблицы
  GET  /{db}/object/{table_id}/?F_I={id}&JSON — получить одну запись
  POST /{db}/object/{table_id}?JSON — создать запись

Конфигурация через .env:
  INTEGRAM_URL      — базовый URL (https://ai2o.ru)
  INTEGRAM_DB       — имя базы (bibot)
  INTEGRAM_LOGIN    — логин
  INTEGRAM_PASSWORD — пароль
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

_BASE_URL = os.getenv("INTEGRAM_URL", "https://ai2o.ru").rstrip("/")
_DB = os.getenv("INTEGRAM_DB", "bibot")
_LOGIN = os.getenv("INTEGRAM_LOGIN", "bibot")
_PASSWORD = os.getenv("INTEGRAM_PASSWORD", "")

# ---------------------------------------------------------------------------
# ID таблиц и реквизитов (из CRM-схемы)
# ---------------------------------------------------------------------------

TABLE_ORDERS = 1024
TABLE_CLIENTS = 1023
TABLE_PRODUCTS = 1022
TABLE_ORDER_ITEMS = 1025
TABLE_CATEGORIES = 1018
TABLE_SOURCES = 1019
TABLE_STATUSES = 1020
TABLE_DELIVERY = 1021

# Реквизиты заказов
REQ_ORDER_DATE = "1048"
REQ_ORDER_ADDRESS = "1050"
REQ_ORDER_DELIVERY_COST = "1052"
REQ_ORDER_ITEMS_TOTAL = "1054"
REQ_ORDER_TOTAL = "1056"
REQ_ORDER_TRACKING = "1058"
REQ_ORDER_COMMENT = "1059"
REQ_ORDER_CLIENT = "1071"
REQ_ORDER_STATUS = "1073"
REQ_ORDER_DELIVERY_METHOD = "1075"
REQ_ORDER_SOURCE = "1076"
REQ_ORDER_MESSENGER = "1388"

# Реквизиты клиентов
REQ_CLIENT_PHONE = "1036"
REQ_CLIENT_TG_ID = "1038"
REQ_CLIENT_TG_USER = "1040"
REQ_CLIENT_ADDRESS = "1042"
REQ_CLIENT_CITY = "1044"
REQ_CLIENT_COMMENT = "1046"
REQ_CLIENT_SOURCE = "1069"

# Реквизиты товаров
REQ_PRODUCT_PRICE = "1027"
REQ_PRODUCT_WEIGHT = "1029"
REQ_PRODUCT_DESC = "1031"
REQ_PRODUCT_INSTOCK = "1033"
REQ_PRODUCT_SKU = "1035"
REQ_PRODUCT_CATEGORY = "1067"
REQ_PRODUCT_SHORT = "1173"


class IntegramAPIError(Exception):
    """Ошибка при работе с Integram API."""


# Названия месяцев → номер (для парсинга из имени заказа)
_MONTH_MAP = {
    "январ": 1, "феврал": 2, "март": 3, "марта": 3,
    "апрел": 4, "ма": 5, "мая": 5, "май": 5,
    "июн": 6, "июл": 7, "август": 8,
    "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}


def _detect_month(order_name: str, date_str: str) -> str:
    """Определить месяц заказа в формате 'MM.YYYY'.

    Приоритет:
    1. Из имени заказа: '(Март 26)', 'февраль 26', etc.
    2. Из даты (DD.MM.YYYY ...) если есть.
    3. Пустая строка если не удалось определить.
    """
    if order_name:
        name_lower = order_name.lower()
        # Паттерн: "(Март 26)" или "(Октябрь 25)"
        m = re.search(r'\((\S+)\s+(\d{2,4})\)', name_lower)
        if m:
            month_num = _match_month(m.group(1))
            if month_num:
                year = _normalize_year(m.group(2))
                return f"{month_num:02d}.{year}"
        # Паттерн: "февраль 26" (всё имя — месяц + год)
        m = re.search(r'^(\S+)\s+(\d{2,4})$', name_lower.strip())
        if m:
            month_num = _match_month(m.group(1))
            if month_num:
                year = _normalize_year(m.group(2))
                return f"{month_num:02d}.{year}"

    # Fallback: из даты "DD.MM.YYYY ..."
    if date_str:
        parts = date_str.split(".")
        if len(parts) >= 3:
            try:
                mm = int(parts[1])
                yyyy = int(parts[2].split()[0])
                if 1 <= mm <= 12 and yyyy > 2000:
                    return f"{mm:02d}.{yyyy}"
            except (ValueError, IndexError):
                pass

    return ""


def _match_month(text: str) -> Optional[int]:
    """Найти номер месяца по началу слова."""
    text = text.lower().rstrip("ьяеи")
    for prefix, num in _MONTH_MAP.items():
        if text.startswith(prefix) or prefix.startswith(text):
            return num
    return None


def _normalize_year(y: str) -> int:
    """'26' → 2026, '2025' → 2025."""
    n = int(y)
    return n + 2000 if n < 100 else n


def _strip_html(text: str) -> str:
    """Убрать HTML-теги из значения реквизита."""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', text)
    return clean.strip()


def _extract_ref_text(html: str) -> str:
    """Извлечь текст из HTML-ссылки типа <A HREF="...">Текст</A>."""
    if not html:
        return ""
    m = re.search(r'>([^<]+)<', html)
    return m.group(1).strip() if m else _strip_html(html)


def _extract_ref_id(html: str) -> Optional[int]:
    """Извлечь ID из ссылки типа <A HREF="/bibot/object/1023/?F_I=1137">."""
    if not html:
        return None
    m = re.search(r'F_I=(\d+)', html)
    return int(m.group(1)) if m else None


class IntegramAPI:
    """Синхронный/асинхронный клиент для реального Integram API."""

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._xsrf: Optional[str] = None
        self._http: Optional[httpx.AsyncClient] = None

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=_BASE_URL,
                timeout=30.0,
            )
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    async def authenticate(self) -> None:
        """Авторизация: POST /{db}/auth?JSON."""
        http = await self._get_http()
        resp = await http.post(
            f"/{_DB}/auth?JSON",
            data={"login": _LOGIN, "pwd": _PASSWORD},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()
        if "token" not in data:
            raise IntegramAPIError(f"Ошибка авторизации: {data}")
        self._token = data["token"]
        self._xsrf = data.get("_xsrf", "")
        logger.info("Integram авторизация OK (user_id=%s)", data.get("id"))

    async def _get_table_page(
        self,
        table_id: int,
        pg: int = 1,
    ) -> dict:
        """Получить страницу таблицы (pg=1 — первая)."""
        http = await self._get_http()
        url = f"/{_DB}/object/{table_id}/?JSON&F_U=1&pg={pg}"
        resp = await http.get(url, cookies={_DB: self._token or ""})
        resp.raise_for_status()
        return resp.json()

    async def get_all_objects(self, table_id: int) -> list[dict[str, Any]]:
        """Получить все записи таблицы (все страницы).

        Возвращает список dict с ключами: id, val, reqs (dict реквизитов).
        """
        all_objects: list[dict[str, Any]] = []
        pg = 1
        page_size = 20
        while True:
            data = await self._get_table_page(table_id, pg=pg)

            # Объекты (id, val)
            objects = data.get("object", [])
            if not objects:
                break

            # Реквизиты: {"object_id": ["val1", "val2", ...], ...}
            reqs = data.get("&object_reqs", {})
            # Заголовки реквизитов (порядок полей)
            head_data = {}
            for key, val in data.items():
                if "&uni_obj_head" in key and "filter" not in key:
                    head_data = val
                    break
            req_ids = head_data.get("typ", [])

            for obj in objects:
                obj_id = str(obj.get("id", ""))
                obj_val = obj.get("val", "")
                obj_reqs_raw = reqs.get(obj_id, [])

                obj_reqs = {}
                for i, req_id in enumerate(req_ids):
                    if i < len(obj_reqs_raw):
                        obj_reqs[req_id] = obj_reqs_raw[i]

                all_objects.append({
                    "id": int(obj_id) if obj_id.isdigit() else 0,
                    "val": obj_val,
                    "reqs": obj_reqs,
                })

            if len(objects) < page_size:
                break
            pg += 1

        return all_objects

    # ------------------------------------------------------------------
    # Высокоуровневые методы для веб-панели
    # ------------------------------------------------------------------

    async def get_orders(self) -> list[dict[str, Any]]:
        """Получить все заказы в удобном формате."""
        raw = await self.get_all_objects(TABLE_ORDERS)
        orders = []
        for obj in raw:
            r = obj["reqs"]
            order_name = obj["val"]
            orders.append({
                "id": obj["id"],
                "number": order_name,
                "month": _detect_month(order_name, _strip_html(r.get(REQ_ORDER_DATE, ""))),
                "date": _strip_html(r.get(REQ_ORDER_DATE, "")),
                "client_name": _extract_ref_text(r.get(REQ_ORDER_CLIENT, "")),
                "client_id": _extract_ref_id(r.get(REQ_ORDER_CLIENT, "")),
                "status": _extract_ref_text(r.get(REQ_ORDER_STATUS, "")),
                "delivery_method": _extract_ref_text(r.get(REQ_ORDER_DELIVERY_METHOD, "")),
                "source": _extract_ref_text(r.get(REQ_ORDER_SOURCE, "")),
                "delivery_address": _strip_html(r.get(REQ_ORDER_ADDRESS, "")),
                "delivery_cost": _parse_number(r.get(REQ_ORDER_DELIVERY_COST, "")),
                "items_total": _parse_number(r.get(REQ_ORDER_ITEMS_TOTAL, "")),
                "total": _parse_number(r.get(REQ_ORDER_TOTAL, "")),
                "tracking_number": _strip_html(r.get(REQ_ORDER_TRACKING, "")),
                "comment": _strip_html(r.get(REQ_ORDER_COMMENT, "")),
                "messenger": _strip_html(r.get(REQ_ORDER_MESSENGER, "")),
            })
        return orders

    async def get_clients(self) -> list[dict[str, Any]]:
        """Получить всех клиентов."""
        raw = await self.get_all_objects(TABLE_CLIENTS)
        clients = []
        for obj in raw:
            r = obj["reqs"]
            clients.append({
                "id": obj["id"],
                "name": obj["val"],
                "phone": _strip_html(r.get(REQ_CLIENT_PHONE, "")),
                "telegram_id": _strip_html(r.get(REQ_CLIENT_TG_ID, "")),
                "telegram_username": _strip_html(r.get(REQ_CLIENT_TG_USER, "")),
                "address": _strip_html(r.get(REQ_CLIENT_ADDRESS, "")),
                "city": _strip_html(r.get(REQ_CLIENT_CITY, "")),
                "source": _extract_ref_text(r.get(REQ_CLIENT_SOURCE, "")),
                "comment": _strip_html(r.get(REQ_CLIENT_COMMENT, "")),
            })
        return clients

    async def get_products(self) -> list[dict[str, Any]]:
        """Получить все товары."""
        raw = await self.get_all_objects(TABLE_PRODUCTS)
        products = []
        for obj in raw:
            r = obj["reqs"]
            products.append({
                "id": obj["id"],
                "name": obj["val"],
                "price": _parse_number(r.get(REQ_PRODUCT_PRICE, "")),
                "weight": _parse_number(r.get(REQ_PRODUCT_WEIGHT, "")),
                "description": _strip_html(r.get(REQ_PRODUCT_DESC, "")),
                "in_stock": _strip_html(r.get(REQ_PRODUCT_INSTOCK, "")) != "",
                "sku_uds": _strip_html(r.get(REQ_PRODUCT_SKU, "")),
                "category": _extract_ref_text(r.get(REQ_PRODUCT_CATEGORY, "")),
                "short_name": _strip_html(r.get(REQ_PRODUCT_SHORT, "")),
            })
        return products

    async def get_dashboard_stats(self) -> dict[str, Any]:
        """Статистика для дашборда."""
        orders = await self.get_orders()
        clients = await self.get_clients()

        total_orders = len(orders)
        total_clients = len(clients)
        total_revenue = sum(o.get("total") or 0.0 for o in orders)
        avg_order = total_revenue / total_orders if total_orders else 0.0
        new_orders = sum(1 for o in orders if o.get("status") == "Новый")
        delivered_orders = sum(1 for o in orders if o.get("status") == "Доставлен")

        return {
            "total_orders": total_orders,
            "total_clients": total_clients,
            "total_revenue": total_revenue,
            "avg_order": round(avg_order),
            "new_orders": new_orders,
            "delivered_orders": delivered_orders,
        }


def _parse_number(val: str) -> Optional[float]:
    """Парсинг числа из строки (может быть пустая или с пробелами)."""
    if not val:
        return None
    clean = _strip_html(val).replace(" ", "").replace(",", ".")
    if not clean:
        return None
    try:
        return float(clean)
    except ValueError:
        return None
