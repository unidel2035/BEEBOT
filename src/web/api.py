"""FastAPI-бэкенд веб-панели управления заказами «Усадьба Дмитровых».

Эндпоинты:
  POST /api/auth/token          — получить JWT по логину/паролю
  GET  /api/auth/me             — текущий пользователь (username, role)
  GET  /api/dashboard           — статистика (admin)
  GET  /api/orders              — список заказов (admin + warehouse)
  GET  /api/orders/{id}         — заказ по ID (admin + warehouse)
  PATCH /api/orders/{id}/status — сменить статус заказа (admin; warehouse ограничен)
  PATCH /api/orders/{id}/tracking — ввести трек-номер (admin)
  GET  /api/clients             — список клиентов (admin)
  GET  /api/clients/{id}        — клиент + история заказов (admin)
  GET  /api/products            — список товаров (admin + warehouse)
  PATCH /api/products/{id}/stock — обновить остаток (admin + warehouse)
  GET  /api/users               — список пользователей (admin)
  POST /api/users               — создать пользователя (admin)
  PATCH /api/users/{id}         — обновить пользователя (admin)
  DELETE /api/users/{id}        — деактивировать пользователя (admin)
  GET  /api/reference           — справочники (admin + warehouse)

Конфигурация через .env:
  WEB_USERNAME  — логин администратора-фоллбэк (по умолчанию: admin)
  WEB_PASSWORD  — пароль администратора-фоллбэк (по умолчанию: changeme)
  WEB_SECRET    — секрет JWT (генерируется при отсутствии)
  WEB_TOKEN_TTL — время жизни токена в минутах (по умолчанию: 60)
  WEB_CORS_ORIGINS — разрешённые домены через запятую (по умолчанию: *)
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.integram_api import (
    IntegramAPI,
    IntegramAPIError,
    REQ_CLIENT_TG_ID,
    TABLE_ORDERS,
    TABLE_ORDER_ITEMS,
    TABLE_PRODUCTS,
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
    REQ_PRODUCT_PRICE,
    REQ_PRODUCT_WEIGHT,
    REQ_PRODUCT_DESC,
    REQ_PRODUCT_INSTOCK,
    REQ_PRODUCT_SKU,
    REQ_PRODUCT_CATEGORY,
    REQ_PRODUCT_SHORT,
    REQ_PRODUCT_STOCK,
)
from src.web.notifications import notify_client_status_change, notify_client_tracking
from src.web.users import (
    get_user_by_username,
    get_all_users,
    create_user,
    update_user as update_user_service,
    delete_user as delete_user_service,
    verify_password,
    VALID_ROLES,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Конфигурация JWT
# ---------------------------------------------------------------------------

_WEB_USERNAME = os.getenv("WEB_USERNAME", "admin")
_WEB_PASSWORD = os.getenv("WEB_PASSWORD", "")
if not _WEB_PASSWORD:
    raise RuntimeError(
        "WEB_PASSWORD не задан! Установите переменную окружения WEB_PASSWORD в .env"
    )
_WEB_SECRET = os.getenv("WEB_SECRET", "")
if not _WEB_SECRET:
    _WEB_SECRET = secrets.token_hex(32)
    logger.warning("WEB_SECRET не задан — сгенерирован случайный ключ (токены сбросятся при перезапуске)")
_TOKEN_TTL = int(os.getenv("WEB_TOKEN_TTL", "60"))  # minutes
_ALGORITHM = "HS256"

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

_CORS_ORIGINS_RAW = os.getenv("WEB_CORS_ORIGINS", "http://185.233.200.13:8088,http://localhost:5173")
_CORS_ORIGINS = [o.strip() for o in _CORS_ORIGINS_RAW.split(",") if o.strip()]

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

app = FastAPI(
    title="BEEBOT — Веб-панель",
    description="Управление заказами «Усадьба Дмитровых»",
    version="2.0.0",
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=429,
        content={"detail": "Слишком много запросов, попробуйте позже"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Не отдавать внутренние traceback клиенту."""
    from fastapi.responses import JSONResponse
    logger.error("Необработанная ошибка: %s %s — %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера"},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
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


class CurrentUser(BaseModel):
    username: str
    role: str  # "admin" | "warehouse"


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
    order_sources: list[str]


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _create_token(username: str, role: str = "admin") -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_TTL)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, _WEB_SECRET, algorithm=_ALGORITHM)


async def _get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
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
        role = payload.get("role", "admin")
    except JWTError:
        raise credentials_exc
    return CurrentUser(username=username, role=role)


def _require_role(*roles: str):
    """Фабрика зависимостей: проверить что роль пользователя в списке."""
    async def checker(user: CurrentUser = Depends(_get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав",
            )
        return user
    return checker


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
    """Получить JWT-токен по логину и паролю."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверный логин или пароль",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Попробовать найти пользователя в CRM
    try:
        integram = await _get_integram()
        try:
            user = await get_user_by_username(integram, form_data.username)
        finally:
            await integram.close()

        if user and user.get("active") and verify_password(form_data.password, user["password_hash"]):
            token = _create_token(user["username"], role=user["role"])
            return TokenResponse(access_token=token)
    except Exception as e:
        logger.warning("Ошибка поиска пользователя в CRM: %s", e)

    # 2. Фоллбэк: проверить env-переменные (для обратной совместимости)
    if form_data.username == _WEB_USERNAME and form_data.password == _WEB_PASSWORD:
        token = _create_token(form_data.username, role="admin")
        return TokenResponse(access_token=token)

    raise credentials_exc


@app.get("/api/auth/me", tags=["auth"])
async def get_me(user: CurrentUser = Depends(_get_current_user)) -> dict:
    """Информация о текущем пользователе."""
    return {"username": user.username, "role": user.role}


# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------

from src.crm_constants import (
    STATUS_IDS,
    DELIVERY_IDS as DELIVERY_METHOD_IDS,
    CATEGORY_IDS,
    ORDER_STATUSES,
    DELIVERY_METHODS,
)

@app.get("/api/reference", response_model=ReferenceData, tags=["reference"])
async def get_reference(
    _: CurrentUser = Depends(_require_role("admin", "warehouse")),
) -> ReferenceData:
    return ReferenceData(
        order_statuses=ORDER_STATUSES,
        delivery_methods=DELIVERY_METHODS,
        order_sources=list(SOURCE_IDS.keys()),
    )


# ---------------------------------------------------------------------------
# Дашборд
# ---------------------------------------------------------------------------

@app.get("/api/dashboard", response_model=DashboardStats, tags=["dashboard"])
async def get_dashboard(
    _: CurrentUser = Depends(_require_role("admin")),
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
        raise HTTPException(status_code=502, detail="Ошибка CRM")


@app.get("/api/dashboard/charts", tags=["dashboard"])
async def get_dashboard_charts(
    _: CurrentUser = Depends(_require_role("admin")),
) -> dict[str, Any]:
    """Данные для графиков дашборда: выручка по месяцам, воронка статусов, доставка."""
    import re
    from collections import defaultdict

    try:
        integram = await _get_integram()
        try:
            orders = await integram.get_orders()

            # --- Выручка и количество заказов по месяцам ---
            monthly_revenue: dict[str, float] = defaultdict(float)
            monthly_count: dict[str, int] = defaultdict(int)
            for o in orders:
                # Дата в формате "DD.MM.YYYY HH:MM:SS"
                date_str = o.get("date", "")
                month_key = None
                if date_str:
                    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", date_str)
                    if m:
                        month_key = f"{m.group(3)}-{m.group(2)}"
                # Отфильтровать мусорные даты (только 2024-2030)
                if month_key and "2024" <= month_key <= "2030":
                    monthly_revenue[month_key] += o.get("total") or 0
                    monthly_count[month_key] += 1

            # Сортировать по ключу (YYYY-MM)
            sorted_months = sorted(monthly_revenue.keys())
            month_labels = []
            _MONTH_NAMES = {
                "01": "Янв", "02": "Фев", "03": "Мар", "04": "Апр",
                "05": "Май", "06": "Июн", "07": "Июл", "08": "Авг",
                "09": "Сен", "10": "Окт", "11": "Ноя", "12": "Дек",
            }
            for mk in sorted_months:
                parts = mk.split("-")
                if len(parts) == 2:
                    month_labels.append(f"{_MONTH_NAMES.get(parts[1], parts[1])} {parts[0][-2:]}")
                else:
                    month_labels.append(mk)

            revenue_data = [monthly_revenue[m] for m in sorted_months]
            count_data = [monthly_count[m] for m in sorted_months]

            # --- Воронка статусов ---
            status_counts: dict[str, int] = defaultdict(int)
            for o in orders:
                s = o.get("status", "Неизвестно")
                status_counts[s] += 1

            funnel_labels = ORDER_STATUSES
            funnel_data = [status_counts.get(s, 0) for s in funnel_labels]

            # --- Способы доставки ---
            delivery_counts: dict[str, int] = defaultdict(int)
            for o in orders:
                dm = o.get("delivery_method") or "Не указан"
                delivery_counts[dm] += 1

            delivery_labels = list(delivery_counts.keys())
            delivery_data = [delivery_counts[k] for k in delivery_labels]

            return {
                "monthly": {
                    "labels": month_labels,
                    "revenue": revenue_data,
                    "count": count_data,
                },
                "funnel": {
                    "labels": funnel_labels,
                    "data": funnel_data,
                },
                "delivery": {
                    "labels": delivery_labels,
                    "data": delivery_data,
                },
            }
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


# ---------------------------------------------------------------------------
# Заказы
# ---------------------------------------------------------------------------

@app.get("/api/orders", tags=["orders"])
async def list_orders(
    status: Optional[str] = None,
    source: Optional[str] = None,
    client_id: Optional[int] = None,
    user: CurrentUser = Depends(_require_role("admin", "warehouse")),
) -> list[dict[str, Any]]:
    """Список заказов."""
    try:
        integram = await _get_integram()
        try:
            orders = await integram.get_orders()
            if status:
                orders = [o for o in orders if o.get("status") == status]
            if source:
                orders = [o for o in orders if o.get("source") == source]
            if client_id:
                orders = [o for o in orders if o.get("client_id") == client_id]
            return orders
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(status_code=502, detail="Ошибка CRM")


@app.get("/api/orders/{order_id}", tags=["orders"])
async def get_order(
    order_id: int,
    _: CurrentUser = Depends(_require_role("admin", "warehouse")),
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
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(status_code=502, detail="Ошибка CRM")


# ---------------------------------------------------------------------------
# Обновление заказов (статус, трек-номер)
# ---------------------------------------------------------------------------

EDITABLE_STATUSES = {"Новый", "Подтверждён", "В сборке"}


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


# Переходы статусов, доступные складу
_WAREHOUSE_STATUS_TRANSITIONS = {
    ("Подтверждён", "В сборке"),
    ("В сборке", "Отправлен"),
}


@app.patch("/api/orders/{order_id}/status", tags=["orders"])
async def update_order_status(
    order_id: int,
    body: StatusUpdate,
    user: CurrentUser = Depends(_require_role("admin", "warehouse")),
) -> dict:
    """Сменить статус заказа и уведомить клиента в Telegram."""
    if body.status not in STATUS_IDS:
        raise HTTPException(400, f"Неизвестный статус: {body.status}")
    try:
        integram = await _get_integram()
        try:
            # Проверка прав warehouse: только разрешённые переходы
            if user.role == "warehouse":
                order = await _find_order(integram, order_id)
                if not order:
                    raise HTTPException(404, "Заказ не найден")
                current_status = order.get("status", "")
                if (current_status, body.status) not in _WAREHOUSE_STATUS_TRANSITIONS:
                    raise HTTPException(403, f"Склад не может менять статус с «{current_status}» на «{body.status}»")

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
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


@app.patch("/api/orders/{order_id}/tracking", tags=["orders"])
async def update_order_tracking(
    order_id: int,
    body: TrackingUpdate,
    _: CurrentUser = Depends(_require_role("admin")),
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
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


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
    _: CurrentUser = Depends(_require_role("admin")),
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
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


# ---------------------------------------------------------------------------
# Позиции заказа
# ---------------------------------------------------------------------------


@app.get("/api/orders/{order_id}/items", tags=["order-items"])
async def get_order_items(
    order_id: int,
    _: CurrentUser = Depends(_require_role("admin", "warehouse")),
) -> list[dict]:
    """Получить позиции заказа."""
    try:
        integram = await _get_integram()
        try:
            return await integram.get_order_items(order_id)
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


@app.post("/api/orders/{order_id}/items", tags=["order-items"])
async def add_order_item(
    order_id: int,
    body: ItemCreate,
    _: CurrentUser = Depends(_require_role("admin")),
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
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


@app.patch("/api/orders/{order_id}/items/{item_id}", tags=["order-items"])
async def update_order_item(
    order_id: int,
    item_id: int,
    body: ItemUpdate,
    _: CurrentUser = Depends(_require_role("admin")),
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
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


@app.delete("/api/orders/{order_id}/items/{item_id}", tags=["order-items"])
async def delete_order_item(
    order_id: int,
    item_id: int,
    _: CurrentUser = Depends(_require_role("admin")),
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
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


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
    _: CurrentUser = Depends(_require_role("admin")),
) -> list[dict[str, Any]]:
    """Список всех клиентов."""
    try:
        integram = await _get_integram()
        try:
            return await integram.get_clients()
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(status_code=502, detail="Ошибка CRM")


@app.get("/api/clients/{client_id}", tags=["clients"])
async def get_client(
    client_id: int,
    _: CurrentUser = Depends(_require_role("admin")),
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
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(status_code=502, detail="Ошибка CRM")


# ---------------------------------------------------------------------------
# Товары
# ---------------------------------------------------------------------------

@app.get("/api/products", tags=["products"])
async def list_products(
    in_stock_only: bool = False,
    _: CurrentUser = Depends(_require_role("admin", "warehouse")),
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
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(status_code=502, detail="Ошибка CRM")


# ---------------------------------------------------------------------------
# Товары: CRUD + остатки
# ---------------------------------------------------------------------------

class ProductCreate(BaseModel):
    name: str
    category: Optional[str] = None
    price: Optional[float] = None
    weight: Optional[float] = None
    description: Optional[str] = None
    in_stock: bool = True
    sku_uds: Optional[str] = None
    short_name: Optional[str] = None
    stock: Optional[int] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    weight: Optional[float] = None
    description: Optional[str] = None
    in_stock: Optional[bool] = None
    sku_uds: Optional[str] = None
    short_name: Optional[str] = None
    stock: Optional[int] = None


class StockUpdate(BaseModel):
    stock: int


@app.post("/api/products", tags=["products"])
async def create_product(
    body: ProductCreate,
    _: CurrentUser = Depends(_require_role("admin")),
) -> dict:
    """Создать товар."""
    try:
        integram = await _get_integram()
        try:
            reqs: dict[str, str] = {}
            if body.price is not None:
                reqs[REQ_PRODUCT_PRICE] = str(body.price)
            if body.weight is not None:
                reqs[REQ_PRODUCT_WEIGHT] = str(body.weight)
            if body.description:
                reqs[REQ_PRODUCT_DESC] = body.description
            if body.in_stock:
                reqs[REQ_PRODUCT_INSTOCK] = "1"
            if body.sku_uds:
                reqs[REQ_PRODUCT_SKU] = body.sku_uds
            if body.category and body.category in CATEGORY_IDS:
                reqs[REQ_PRODUCT_CATEGORY] = CATEGORY_IDS[body.category]
            if body.short_name:
                reqs[REQ_PRODUCT_SHORT] = body.short_name
            if body.stock is not None:
                reqs[REQ_PRODUCT_STOCK] = str(body.stock)

            product_id = await integram.create_object(TABLE_PRODUCTS, body.name, reqs)
            return {"ok": True, "product_id": product_id}
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


@app.patch("/api/products/{product_id}", tags=["products"])
async def update_product(
    product_id: int,
    body: ProductUpdate,
    _: CurrentUser = Depends(_require_role("admin")),
) -> dict:
    """Обновить товар."""
    try:
        integram = await _get_integram()
        try:
            reqs: dict[str, str] = {}
            if body.price is not None:
                reqs[REQ_PRODUCT_PRICE] = str(body.price)
            if body.weight is not None:
                reqs[REQ_PRODUCT_WEIGHT] = str(body.weight)
            if body.description is not None:
                reqs[REQ_PRODUCT_DESC] = body.description
            if body.in_stock is not None:
                reqs[REQ_PRODUCT_INSTOCK] = "1" if body.in_stock else ""
            if body.sku_uds is not None:
                reqs[REQ_PRODUCT_SKU] = body.sku_uds
            if body.category is not None:
                cat_id = CATEGORY_IDS.get(body.category)
                if cat_id:
                    reqs[REQ_PRODUCT_CATEGORY] = cat_id
            if body.short_name is not None:
                reqs[REQ_PRODUCT_SHORT] = body.short_name
            if body.stock is not None:
                reqs[REQ_PRODUCT_STOCK] = str(body.stock)

            if body.name is not None:
                # Обновить имя объекта отдельно (val)
                await integram.update_object_value(product_id, body.name)

            if reqs:
                await integram.set_requisites(product_id, TABLE_PRODUCTS, reqs)

            return {"ok": True, "product_id": product_id}
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


@app.delete("/api/products/{product_id}", tags=["products"])
async def delete_product(
    product_id: int,
    _: CurrentUser = Depends(_require_role("admin")),
) -> dict:
    """Снять товар с продажи (in_stock = false)."""
    try:
        integram = await _get_integram()
        try:
            await integram.set_requisites(product_id, TABLE_PRODUCTS, {
                REQ_PRODUCT_INSTOCK: "",
            })
            return {"ok": True, "product_id": product_id}
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


@app.patch("/api/products/{product_id}/stock", tags=["products"])
async def update_product_stock(
    product_id: int,
    body: StockUpdate,
    _: CurrentUser = Depends(_require_role("admin", "warehouse")),
) -> dict:
    """Обновить остаток товара на складе."""
    try:
        integram = await _get_integram()
        try:
            await integram.set_requisites(product_id, TABLE_PRODUCTS, {
                REQ_PRODUCT_STOCK: str(body.stock),
            })
            return {"ok": True, "product_id": product_id, "stock": body.stock}
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


# ---------------------------------------------------------------------------
# Пользователи (только admin)
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    username: str
    password: str
    role: str
    display_name: str = ""


class UserUpdate(BaseModel):
    password: Optional[str] = None
    role: Optional[str] = None
    display_name: Optional[str] = None
    active: Optional[bool] = None


@app.get("/api/users", tags=["users"])
async def list_users(
    _: CurrentUser = Depends(_require_role("admin")),
) -> list[dict[str, Any]]:
    """Список всех пользователей."""
    try:
        integram = await _get_integram()
        try:
            return await get_all_users(integram)
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


@app.post("/api/users", tags=["users"])
async def create_user_endpoint(
    body: UserCreate,
    _: CurrentUser = Depends(_require_role("admin")),
) -> dict:
    """Создать пользователя."""
    if body.role not in VALID_ROLES:
        raise HTTPException(400, f"Недопустимая роль: {body.role}. Допустимые: {', '.join(VALID_ROLES)}")
    try:
        integram = await _get_integram()
        try:
            user_id = await create_user(
                integram,
                username=body.username,
                password=body.password,
                role=body.role,
                display_name=body.display_name,
            )
            return {"ok": True, "user_id": user_id}
        finally:
            await integram.close()
    except ValueError as e:
        raise HTTPException(400, str(e))
    except IntegramAPIError as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


@app.patch("/api/users/{user_id}", tags=["users"])
async def update_user_endpoint(
    user_id: int,
    body: UserUpdate,
    _: CurrentUser = Depends(_require_role("admin")),
) -> dict:
    """Обновить пользователя (роль, пароль, активность)."""
    if body.role is not None and body.role not in VALID_ROLES:
        raise HTTPException(400, f"Недопустимая роль: {body.role}")
    try:
        integram = await _get_integram()
        try:
            await update_user_service(
                integram,
                user_id,
                password=body.password,
                role=body.role,
                display_name=body.display_name,
                active=body.active,
            )
            return {"ok": True, "user_id": user_id}
        finally:
            await integram.close()
    except ValueError as e:
        raise HTTPException(400, str(e))
    except IntegramAPIError as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


@app.delete("/api/users/{user_id}", tags=["users"])
async def delete_user_endpoint(
    user_id: int,
    _: CurrentUser = Depends(_require_role("admin")),
) -> dict:
    """Деактивировать пользователя."""
    try:
        integram = await _get_integram()
        try:
            await delete_user_service(integram, user_id)
            return {"ok": True, "user_id": user_id}
        finally:
            await integram.close()
    except IntegramAPIError as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")
