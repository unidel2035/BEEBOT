"""FastAPI-бэкенд веб-панели управления заказами «Усадьба Дмитровых».

Эндпоинты:
  POST /api/auth/token          — получить JWT по логину/паролю
  GET  /api/dashboard           — статистика (новые заказы, выручка за день/неделю)
  GET  /api/orders              — список заказов (фильтр по статусу, клиенту)
  GET  /api/orders/{id}         — заказ по ID
  PATCH /api/orders/{id}/status   — сменить статус заказа
  PATCH /api/orders/{id}/tracking — ввести трек-номер
  GET  /api/clients             — список клиентов
  GET  /api/clients/{id}        — клиент + история заказов
  GET  /api/products            — список товаров
  GET  /api/reference           — справочники (статусы, способы доставки)

Конфигурация через .env:
  WEB_USERNAME  — логин администратора (по умолчанию: admin)
  WEB_PASSWORD  — пароль администратора (по умолчанию: changeme)
  WEB_SECRET    — секрет JWT (по умолчанию: dev-secret-change-in-production)
  WEB_TOKEN_TTL — время жизни токена в минутах (по умолчанию: 60)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel

from src.integram_api import (
    IntegramAPI,
    IntegramAPIError,
    REQ_CLIENT_TG_ID,
    TABLE_ORDERS,
    TABLE_ORDER_ITEMS,
    REQ_ORDER_STATUS,
    REQ_ORDER_TRACKING,
    REQ_ORDER_ADDRESS,
    REQ_ORDER_DELIVERY_COST,
    REQ_ORDER_DELIVERY_METHOD,
    REQ_ORDER_COMMENT,
    REQ_ORDER_ITEMS_TOTAL,
    REQ_ORDER_TOTAL,
    REQ_ITEM_ORDER,
    REQ_ITEM_PRODUCT,
    REQ_ITEM_QTY,
    REQ_ITEM_PRICE,
    REQ_ITEM_SUM,
)
from src.web.notifications import notify_client_status_change, notify_client_tracking

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Конфигурация JWT
# ---------------------------------------------------------------------------

_WEB_USERNAME = os.getenv("WEB_USERNAME", "admin")
_WEB_PASSWORD = os.getenv("WEB_PASSWORD", "changeme")
_WEB_SECRET = os.getenv("WEB_SECRET", "dev-secret-change-in-production")
_TOKEN_TTL = int(os.getenv("WEB_TOKEN_TTL", "60"))  # minutes
_ALGORITHM = "HS256"

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="BEEBOT — Веб-панель",
    description="Управление заказами «Усадьба Дмитровых»",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

# ---------------------------------------------------------------------------
# Pydantic-схемы
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DashboardStats(BaseModel):
    total_orders: int
    total_clients: int
    total_revenue: float
    avg_order: float
    new_orders: int
    delivered_orders: int


class ReferenceData(BaseModel):
    order_statuses: list[str]
    delivery_methods: list[str]


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _create_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_TTL)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, _WEB_SECRET, algorithm=_ALGORITHM)


async def _get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверный или просроченный токен",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, _WEB_SECRET, algorithms=[_ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc
    return username


# ---------------------------------------------------------------------------
# Хелпер: аутентифицированный Integram-клиент
# ---------------------------------------------------------------------------

async def _get_integram() -> IntegramAPI:
    client = IntegramAPI()
    await client.authenticate()
    return client


async def _find_order(integram: IntegramAPI, order_id: int) -> Optional[dict]:
    """Найти заказ по ID (среди всех заказов)."""
    orders = await integram.get_orders()
    for o in orders:
        if o["id"] == order_id:
            return o
    return None


async def _get_client_telegram_id(integram: IntegramAPI, client_id: Optional[int]) -> Optional[int]:
    """Получить Telegram ID клиента по его ID в CRM."""
    if not client_id:
        return None
    clients = await integram.get_clients()
    for c in clients:
        if c["id"] == client_id:
            tg_id = c.get("telegram_id", "")
            if tg_id:
                try:
                    return int(tg_id)
                except (ValueError, TypeError):
                    return None
    return None


# ---------------------------------------------------------------------------
# Аутентификация
# ---------------------------------------------------------------------------

@app.post("/api/auth/token", response_model=TokenResponse, tags=["auth"])
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    """Получить JWT-токен по логину и паролю администратора."""
    if form_data.username != _WEB_USERNAME or form_data.password != _WEB_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = _create_token(form_data.username)
    return TokenResponse(access_token=token)


# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------

ORDER_STATUSES = ["Новый", "Подтверждён", "В сборке", "Отправлен", "Доставлен", "Отменён"]
DELIVERY_METHODS = ["СДЭК", "Почта России", "Самовывоз"]

@app.get("/api/reference", response_model=ReferenceData, tags=["reference"])
async def get_reference(
    _: str = Depends(_get_current_user),
) -> ReferenceData:
    return ReferenceData(
        order_statuses=ORDER_STATUSES,
        delivery_methods=DELIVERY_METHODS,
    )


# ---------------------------------------------------------------------------
# Дашборд
# ---------------------------------------------------------------------------

@app.get("/api/dashboard", response_model=DashboardStats, tags=["dashboard"])
async def get_dashboard(
    _: str = Depends(_get_current_user),
) -> DashboardStats:
    """Статистика за день и неделю."""
    try:
        integram = await _get_integram()
        try:
            stats = await integram.get_dashboard_stats()
            return DashboardStats(**stats)
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(status_code=502, detail=f"Ошибка CRM: {exc}")


# ---------------------------------------------------------------------------
# Заказы
# ---------------------------------------------------------------------------

@app.get("/api/orders", tags=["orders"])
async def list_orders(
    status: Optional[str] = None,
    client_id: Optional[int] = None,
    _: str = Depends(_get_current_user),
) -> list[dict[str, Any]]:
    """Список заказов."""
    try:
        integram = await _get_integram()
        try:
            orders = await integram.get_orders()
            if status:
                orders = [o for o in orders if o.get("status") == status]
            if client_id:
                orders = [o for o in orders if o.get("client_id") == client_id]
            return orders
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка CRM: {exc}")


@app.get("/api/orders/{order_id}", tags=["orders"])
async def get_order(
    order_id: int,
    _: str = Depends(_get_current_user),
) -> dict[str, Any]:
    """Получить заказ по ID с позициями."""
    try:
        integram = await _get_integram()
        try:
            orders = await integram.get_orders()
            for o in orders:
                if o["id"] == order_id:
                    o["items"] = await integram.get_order_items(order_id)
                    o["editable"] = o.get("status") in EDITABLE_STATUSES
                    return o
            raise HTTPException(status_code=404, detail="Заказ не найден")
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка CRM: {exc}")


# ---------------------------------------------------------------------------
# Обновление заказов (статус, трек-номер)
# ---------------------------------------------------------------------------

STATUS_IDS = {
    "Новый": "1086",
    "Подтверждён": "1087",
    "В сборке": "1088",
    "Отправлен": "1089",
    "Доставлен": "1090",
    "Отменён": "1091",
}


EDITABLE_STATUSES = {"Новый", "Подтверждён", "В сборке"}

DELIVERY_METHOD_IDS = {
    "СДЭК": "1092",
    "Почта России": "1093",
    "Самовывоз": "1094",
}


class StatusUpdate(BaseModel):
    status: str


class TrackingUpdate(BaseModel):
    tracking_number: str


class OrderUpdate(BaseModel):
    delivery_address: Optional[str] = None
    delivery_method: Optional[str] = None
    delivery_cost: Optional[float] = None
    comment: Optional[str] = None


class ItemCreate(BaseModel):
    product_id: int
    quantity: int = 1
    unit_price: float


class ItemUpdate(BaseModel):
    quantity: Optional[int] = None
    unit_price: Optional[float] = None


@app.patch("/api/orders/{order_id}/status", tags=["orders"])
async def update_order_status(
    order_id: int,
    body: StatusUpdate,
    _: str = Depends(_get_current_user),
) -> dict:
    """Сменить статус заказа и уведомить клиента в Telegram."""
    if body.status not in STATUS_IDS:
        raise HTTPException(400, f"Неизвестный статус: {body.status}")
    try:
        integram = await _get_integram()
        try:
            await integram.set_requisites(order_id, TABLE_ORDERS, {
                REQ_ORDER_STATUS: STATUS_IDS[body.status],
            })

            # Уведомить клиента в Telegram
            notified = False
            try:
                order = await _find_order(integram, order_id)
                if order:
                    tg_id = await _get_client_telegram_id(integram, order.get("client_id"))
                    if tg_id:
                        notified = await notify_client_status_change(
                            telegram_id=tg_id,
                            order_number=order.get("number", str(order_id)),
                            new_status=body.status,
                            tracking_number=order.get("tracking_number"),
                        )
            except Exception as e:
                logger.warning("Не удалось уведомить клиента: %s", e)

            return {"ok": True, "order_id": order_id, "status": body.status, "notified": notified}
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        raise HTTPException(502, f"Ошибка CRM: {exc}")


@app.patch("/api/orders/{order_id}/tracking", tags=["orders"])
async def update_order_tracking(
    order_id: int,
    body: TrackingUpdate,
    _: str = Depends(_get_current_user),
) -> dict:
    """Ввести трек-номер и уведомить клиента."""
    try:
        integram = await _get_integram()
        try:
            await integram.set_requisites(order_id, TABLE_ORDERS, {
                REQ_ORDER_TRACKING: body.tracking_number,
            })

            # Уведомить клиента
            notified = False
            try:
                order = await _find_order(integram, order_id)
                if order:
                    tg_id = await _get_client_telegram_id(integram, order.get("client_id"))
                    if tg_id:
                        notified = await notify_client_tracking(
                            telegram_id=tg_id,
                            order_number=order.get("number", str(order_id)),
                            tracking_number=body.tracking_number,
                        )
            except Exception as e:
                logger.warning("Не удалось уведомить клиента: %s", e)

            return {"ok": True, "order_id": order_id, "tracking_number": body.tracking_number, "notified": notified}
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        raise HTTPException(502, f"Ошибка CRM: {exc}")


# ---------------------------------------------------------------------------
# Редактирование заказа (до отправки)
# ---------------------------------------------------------------------------


async def _check_editable(integram: IntegramAPI, order_id: int) -> dict:
    """Проверить, что заказ существует и доступен для редактирования."""
    order = await _find_order(integram, order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    if order.get("status") not in EDITABLE_STATUSES:
        raise HTTPException(
            409,
            f"Заказ в статусе «{order.get('status')}» нельзя редактировать",
        )
    return order


@app.patch("/api/orders/{order_id}", tags=["orders"])
async def update_order(
    order_id: int,
    body: OrderUpdate,
    _: str = Depends(_get_current_user),
) -> dict:
    """Обновить поля заказа (адрес, доставку, комментарий)."""
    try:
        integram = await _get_integram()
        try:
            await _check_editable(integram, order_id)

            reqs: dict[str, str] = {}
            if body.delivery_address is not None:
                reqs[REQ_ORDER_ADDRESS] = body.delivery_address
            if body.delivery_method is not None:
                mid = DELIVERY_METHOD_IDS.get(body.delivery_method)
                if not mid:
                    raise HTTPException(400, f"Неизвестный способ доставки: {body.delivery_method}")
                reqs[REQ_ORDER_DELIVERY_METHOD] = mid
            if body.delivery_cost is not None:
                reqs[REQ_ORDER_DELIVERY_COST] = str(body.delivery_cost)
                # Пересчитать итого
                order = await _find_order(integram, order_id)
                items_total = order.get("items_total") or 0
                reqs[REQ_ORDER_TOTAL] = str(items_total + body.delivery_cost)
            if body.comment is not None:
                reqs[REQ_ORDER_COMMENT] = body.comment

            if reqs:
                await integram.set_requisites(order_id, TABLE_ORDERS, reqs)

            return {"ok": True, "order_id": order_id}
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        raise HTTPException(502, f"Ошибка CRM: {exc}")


# ---------------------------------------------------------------------------
# Позиции заказа
# ---------------------------------------------------------------------------


@app.get("/api/orders/{order_id}/items", tags=["order-items"])
async def get_order_items(
    order_id: int,
    _: str = Depends(_get_current_user),
) -> list[dict]:
    """Получить позиции заказа."""
    try:
        integram = await _get_integram()
        try:
            return await integram.get_order_items(order_id)
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        raise HTTPException(502, f"Ошибка CRM: {exc}")


@app.post("/api/orders/{order_id}/items", tags=["order-items"])
async def add_order_item(
    order_id: int,
    body: ItemCreate,
    _: str = Depends(_get_current_user),
) -> dict:
    """Добавить позицию к заказу."""
    try:
        integram = await _get_integram()
        try:
            await _check_editable(integram, order_id)

            item_reqs = {
                REQ_ITEM_ORDER: str(order_id),
                REQ_ITEM_PRODUCT: str(body.product_id),
                REQ_ITEM_QTY: str(body.quantity),
                REQ_ITEM_PRICE: str(body.unit_price),
                REQ_ITEM_SUM: str(body.quantity * body.unit_price),
            }
            item_id = await integram.create_object(
                TABLE_ORDER_ITEMS, "Позиция заказа", item_reqs,
            )

            # Пересчитать итого заказа
            await _recalculate_totals(integram, order_id)

            return {"ok": True, "item_id": item_id}
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        raise HTTPException(502, f"Ошибка CRM: {exc}")


@app.patch("/api/orders/{order_id}/items/{item_id}", tags=["order-items"])
async def update_order_item(
    order_id: int,
    item_id: int,
    body: ItemUpdate,
    _: str = Depends(_get_current_user),
) -> dict:
    """Изменить количество/цену позиции."""
    try:
        integram = await _get_integram()
        try:
            await _check_editable(integram, order_id)

            # Получить текущую позицию для пересчёта суммы
            items = await integram.get_order_items(order_id)
            current = next((i for i in items if i["id"] == item_id), None)
            if not current:
                raise HTTPException(404, "Позиция не найдена")

            qty = body.quantity if body.quantity is not None else current["quantity"]
            price = body.unit_price if body.unit_price is not None else current["unit_price"]

            reqs = {
                REQ_ITEM_QTY: str(qty),
                REQ_ITEM_PRICE: str(price),
                REQ_ITEM_SUM: str(qty * price),
            }
            await integram.set_requisites(item_id, TABLE_ORDER_ITEMS, reqs)

            await _recalculate_totals(integram, order_id)

            return {"ok": True, "item_id": item_id}
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        raise HTTPException(502, f"Ошибка CRM: {exc}")


@app.delete("/api/orders/{order_id}/items/{item_id}", tags=["order-items"])
async def delete_order_item(
    order_id: int,
    item_id: int,
    _: str = Depends(_get_current_user),
) -> dict:
    """Удалить позицию из заказа."""
    try:
        integram = await _get_integram()
        try:
            await _check_editable(integram, order_id)

            await integram.delete_object(item_id)
            await _recalculate_totals(integram, order_id)

            return {"ok": True, "item_id": item_id}
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        raise HTTPException(502, f"Ошибка CRM: {exc}")


async def _recalculate_totals(integram: IntegramAPI, order_id: int) -> None:
    """Пересчитать суммы заказа на основе позиций."""
    items = await integram.get_order_items(order_id)
    items_total = sum(i["quantity"] * i["unit_price"] for i in items)

    order = await _find_order(integram, order_id)
    delivery_cost = (order.get("delivery_cost") or 0) if order else 0
    total = items_total + delivery_cost

    await integram.set_requisites(order_id, TABLE_ORDERS, {
        REQ_ORDER_ITEMS_TOTAL: str(items_total),
        REQ_ORDER_TOTAL: str(total),
    })


# ---------------------------------------------------------------------------
# Клиенты
# ---------------------------------------------------------------------------

@app.get("/api/clients", tags=["clients"])
async def list_clients(
    _: str = Depends(_get_current_user),
) -> list[dict[str, Any]]:
    """Список всех клиентов."""
    try:
        integram = await _get_integram()
        try:
            return await integram.get_clients()
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка CRM: {exc}")


@app.get("/api/clients/{client_id}", tags=["clients"])
async def get_client(
    client_id: int,
    _: str = Depends(_get_current_user),
) -> dict[str, Any]:
    """Клиент + история заказов."""
    try:
        integram = await _get_integram()
        try:
            clients = await integram.get_clients()
            client = None
            for c in clients:
                if c["id"] == client_id:
                    client = c
                    break
            if not client:
                raise HTTPException(status_code=404, detail="Клиент не найден")

            orders = await integram.get_orders()
            client["orders"] = [o for o in orders if o.get("client_id") == client_id]
            return client
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка CRM: {exc}")


# ---------------------------------------------------------------------------
# Товары
# ---------------------------------------------------------------------------

@app.get("/api/products", tags=["products"])
async def list_products(
    in_stock_only: bool = False,
    _: str = Depends(_get_current_user),
) -> list[dict[str, Any]]:
    """Список всех товаров."""
    try:
        integram = await _get_integram()
        try:
            products = await integram.get_products()
            if in_stock_only:
                products = [p for p in products if p.get("in_stock")]
            return products
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка CRM: {exc}")
