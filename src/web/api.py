"""FastAPI-бэкенд веб-панели управления заказами «Усадьба Дмитровых».

Эндпоинты:
  POST /api/auth/token          — получить JWT по логину/паролю
  GET  /api/auth/me             — текущий пользователь (username, role)
  GET  /api/dashboard           — статистика (admin)
  GET  /api/orders              — список заказов (admin + warehouse)
  POST /api/orders              — создать заказ (admin + warehouse)
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

import asyncio
import csv
import io
import json as json_lib
import logging
import os
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.integram_api import IntegramAPIError
from src.integram_client import IntegramClient, IntegramError, IntegramNotFoundError
from src.crm_constants import (
    STATUS_IDS,
    DELIVERY_IDS as DELIVERY_METHOD_IDS,
    SOURCE_IDS,
    ORDER_STATUSES,
    DELIVERY_METHODS,
)
from src.web.notifications import (
    notify_client_status_change,
    notify_client_tracking,
    notify_beekeeper_status_change,
)
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
_INTERNAL_SECRET = os.getenv("WEB_INTERNAL_SECRET", "")

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

_CORS_ORIGINS_RAW = os.getenv("WEB_CORS_ORIGINS", "http://185.233.200.13:8088,http://localhost:5173")
_CORS_ORIGINS = [o.strip() for o in _CORS_ORIGINS_RAW.split(",") if o.strip()]

# ---------------------------------------------------------------------------
# FastAPI app + Rate limiting
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
# Pydantic-схемы запросов/ответов
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


class OrderCreate(BaseModel):
    client_name: str
    phone: Optional[str] = None
    delivery_method: Optional[str] = None
    delivery_address: Optional[str] = None
    delivery_cost: Optional[float] = None
    source: Optional[str] = "Сайт"
    comment: Optional[str] = None
    items: list[ItemCreate] = []


# ---------------------------------------------------------------------------
# Пагинация и поиск
# ---------------------------------------------------------------------------

_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 1000


def _paginate(
    items: list[dict],
    page: int = 1,
    per_page: int = _DEFAULT_PAGE_SIZE,
    search: Optional[str] = None,
    search_fields: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Пагинация + поиск по списку элементов.

    Returns:
        {"items": [...], "total": N, "page": P, "per_page": PP, "pages": T}
    """
    # Текстовый поиск
    if search and search_fields:
        q = search.lower()
        items = [
            item for item in items
            if any(q in str(item.get(f, "")).lower() for f in search_fields)
        ]

    total = len(items)
    per_page = min(max(per_page, 1), _MAX_PAGE_SIZE)
    page = max(page, 1)
    pages = max((total + per_page - 1) // per_page, 1)
    start = (page - 1) * per_page

    return {
        "items": items[start:start + per_page],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


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
# Хелпер: аутентифицированный CRM-клиент
# ---------------------------------------------------------------------------

async def _get_crm() -> IntegramClient:
    """Создать и авторизовать CRM-клиент."""
    client = IntegramClient()
    await client.authenticate()
    return client


EDITABLE_STATUSES = {"Новый", "Подтверждён", "В сборке"}

# Переходы статусов, доступные складу
_WAREHOUSE_STATUS_TRANSITIONS = {
    ("Подтверждён", "В сборке"),
    ("В сборке", "Отправлен"),
}

_MONTH_NAMES = {
    1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр",
    5: "Май", 6: "Июн", 7: "Июл", 8: "Авг",
    9: "Сен", 10: "Окт", 11: "Ноя", 12: "Дек",
}


def _order_to_dict(order) -> dict[str, Any]:
    """Конвертировать Order-модель в dict для JSON-ответа."""
    d = order.model_dump()
    # Дата → строка для фронтенда
    if order.date:
        d["date"] = order.date.strftime("%d.%m.%Y %H:%M:%S")
    # items → list[dict]
    if order.items:
        d["items"] = [i.model_dump() for i in order.items]
    return d


def _client_to_dict(client) -> dict[str, Any]:
    """Конвертировать Client-модель в dict для JSON-ответа."""
    d = client.model_dump()
    # Переименовать full_name → name для совместимости с фронтом
    d["name"] = d.pop("full_name", "")
    return d


def _product_to_dict(product) -> dict[str, Any]:
    """Конвертировать Product-модель в dict для JSON-ответа."""
    return product.model_dump()


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
        crm = await _get_crm()
        try:
            user = await get_user_by_username(crm.api, form_data.username)
        finally:
            await crm.close()

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
    """Статистика."""
    try:
        crm = await _get_crm()
        try:
            stats = await crm.get_dashboard_stats()
            return DashboardStats(**stats)
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(status_code=502, detail="Ошибка CRM")


@app.get("/api/dashboard/charts", tags=["dashboard"])
async def get_dashboard_charts(
    _: CurrentUser = Depends(_require_role("admin")),
) -> dict[str, Any]:
    """Данные для графиков дашборда: выручка по месяцам, воронка статусов, доставка."""
    try:
        crm = await _get_crm()
        try:
            orders = await crm.get_orders()

            # --- Выручка и количество заказов по месяцам ---
            monthly_revenue: dict[str, float] = defaultdict(float)
            monthly_count: dict[str, int] = defaultdict(int)
            for o in orders:
                if o.date and 2024 <= o.date.year <= 2030:
                    month_key = f"{o.date.year}-{o.date.month:02d}"
                    monthly_revenue[month_key] += o.total or 0
                    monthly_count[month_key] += 1

            sorted_months = sorted(monthly_revenue.keys())
            month_labels = []
            for mk in sorted_months:
                year, month = mk.split("-")
                month_labels.append(f"{_MONTH_NAMES.get(int(month), month)} {year[-2:]}")

            revenue_data = [monthly_revenue[m] for m in sorted_months]
            count_data = [monthly_count[m] for m in sorted_months]

            # --- Воронка статусов ---
            status_counts: dict[str, int] = defaultdict(int)
            for o in orders:
                status_counts[o.status or "Неизвестно"] += 1

            funnel_labels = ORDER_STATUSES
            funnel_data = [status_counts.get(s, 0) for s in funnel_labels]

            # --- Способы доставки ---
            delivery_counts: dict[str, int] = defaultdict(int)
            for o in orders:
                delivery_counts[o.delivery_method or "Не указан"] += 1

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
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
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
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = _DEFAULT_PAGE_SIZE,
    user: CurrentUser = Depends(_require_role("admin", "warehouse")),
) -> dict[str, Any]:
    """Список заказов с пагинацией и поиском."""
    try:
        crm = await _get_crm()
        try:
            orders = await crm.get_orders(client_id=client_id, status=status)
            result = [_order_to_dict(o) for o in orders]
            if source:
                result = [o for o in result if o.get("source") == source]
            return _paginate(
                result, page, per_page, search,
                search_fields=["number", "client_name", "delivery_address", "comment"],
            )
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(status_code=502, detail="Ошибка CRM")


@app.post("/api/orders", tags=["orders"], status_code=201)
async def create_order_web(
    body: OrderCreate,
    _: CurrentUser = Depends(_require_role("admin", "warehouse")),
) -> dict[str, Any]:
    """Создать заказ через веб-панель."""
    try:
        crm = await _get_crm()
        try:
            # Найти или создать клиента
            client = await crm.get_or_create_client(
                telegram_id=0,
                full_name=body.client_name,
                phone=body.phone,
                source=body.source or "Сайт",
            )
            items = [
                {"product_id": i.product_id, "quantity": i.quantity, "unit_price": i.unit_price}
                for i in body.items
            ]
            order = await crm.create_order(
                client_id=client.id,
                items=items,
                delivery_method=body.delivery_method or "",
                delivery_address=body.delivery_address,
                delivery_cost=body.delivery_cost or 0,
                source=body.source or "Сайт",
            )
            return _order_to_dict(order)
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram при создании заказа: %s", exc)
        raise HTTPException(status_code=502, detail="Ошибка CRM")


@app.get("/api/orders/{order_id}", tags=["orders"])
async def get_order(
    order_id: int,
    _: CurrentUser = Depends(_require_role("admin", "warehouse")),
) -> dict[str, Any]:
    """Получить заказ по ID с позициями."""
    try:
        crm = await _get_crm()
        try:
            order = await crm.get_order(order_id)
            order.items = await crm.get_order_items(order_id)
            d = _order_to_dict(order)
            d["editable"] = order.status in EDITABLE_STATUSES
            return d
        except IntegramNotFoundError:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(status_code=502, detail="Ошибка CRM")


# ---------------------------------------------------------------------------
# Обновление заказов (статус, трек-номер, поля)
# ---------------------------------------------------------------------------

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
        crm = await _get_crm()
        try:
            # Проверка прав warehouse: только разрешённые переходы
            if user.role == "warehouse":
                try:
                    order = await crm.get_order(order_id)
                except IntegramNotFoundError:
                    raise HTTPException(404, "Заказ не найден")
                if (order.status, body.status) not in _WAREHOUSE_STATUS_TRANSITIONS:
                    raise HTTPException(403, f"Склад не может менять статус с «{order.status}» на «{body.status}»")

            await crm.update_order_status(order_id, body.status)

            # Уведомить клиента в Telegram
            notified = False
            try:
                order = await crm.get_order(order_id)
                if order.client_id:
                    tg_id = await crm.get_client_telegram_id(order.client_id)
                    if tg_id:
                        notified = await notify_client_status_change(
                            telegram_id=tg_id,
                            order_number=order.number or str(order_id),
                            new_status=body.status,
                            tracking_number=order.tracking_number,
                        )
            except Exception as e:
                logger.warning("Не удалось уведомить клиента: %s", e)

            # Уведомить пчеловода
            try:
                await notify_beekeeper_status_change(
                    order_number=order.number if order else str(order_id),
                    new_status=body.status,
                    client_name=order.client_name if order and hasattr(order, "client_name") else "",
                    tracking_number=order.tracking_number if order else None,
                )
            except Exception as e:
                logger.warning("Не удалось уведомить пчеловода: %s", e)

            # SSE: уведомить веб-панель
            await push_event("order_status", {
                "order_id": order_id,
                "order_number": order.number if order else str(order_id),
                "status": body.status,
            })

            return {"ok": True, "order_id": order_id, "status": body.status, "notified": notified}
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
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
        crm = await _get_crm()
        try:
            await crm.update_order(order_id, tracking_number=body.tracking_number)

            # Уведомить клиента
            notified = False
            try:
                order = await crm.get_order(order_id)
                if order.client_id:
                    tg_id = await crm.get_client_telegram_id(order.client_id)
                    if tg_id:
                        notified = await notify_client_tracking(
                            telegram_id=tg_id,
                            order_number=order.number or str(order_id),
                            tracking_number=body.tracking_number,
                        )
            except Exception as e:
                logger.warning("Не удалось уведомить клиента: %s", e)

            # SSE: уведомить веб-панель
            await push_event("order_tracking", {
                "order_id": order_id,
                "tracking_number": body.tracking_number,
            })

            return {"ok": True, "order_id": order_id, "tracking_number": body.tracking_number, "notified": notified}
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


@app.patch("/api/orders/{order_id}", tags=["orders"])
async def update_order(
    order_id: int,
    body: OrderUpdate,
    _: CurrentUser = Depends(_require_role("admin")),
) -> dict:
    """Обновить поля заказа (адрес, доставку, комментарий)."""
    try:
        crm = await _get_crm()
        try:
            # Проверить что заказ доступен для редактирования
            try:
                order = await crm.get_order(order_id)
            except IntegramNotFoundError:
                raise HTTPException(404, "Заказ не найден")
            if order.status not in EDITABLE_STATUSES:
                raise HTTPException(409, f"Заказ в статусе «{order.status}» нельзя редактировать")

            # Валидация способа доставки
            if body.delivery_method is not None and body.delivery_method not in DELIVERY_METHOD_IDS:
                raise HTTPException(400, f"Неизвестный способ доставки: {body.delivery_method}")

            # Собрать kwargs для update_order
            kwargs: dict[str, Any] = {}
            if body.delivery_address is not None:
                kwargs["delivery_address"] = body.delivery_address
            if body.delivery_method is not None:
                kwargs["delivery_method"] = body.delivery_method
            if body.delivery_cost is not None:
                kwargs["delivery_cost"] = body.delivery_cost
                # Пересчитать итого
                kwargs["total"] = (order.items_total or 0) + body.delivery_cost
            if body.comment is not None:
                kwargs["comment"] = body.comment

            if kwargs:
                await crm.update_order(order_id, **kwargs)

            return {"ok": True, "order_id": order_id}
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
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
        crm = await _get_crm()
        try:
            items = await crm.get_order_items(order_id)
            return [i.model_dump() for i in items]
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
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
        crm = await _get_crm()
        try:
            # Проверить что заказ доступен для редактирования
            try:
                order = await crm.get_order(order_id)
            except IntegramNotFoundError:
                raise HTTPException(404, "Заказ не найден")
            if order.status not in EDITABLE_STATUSES:
                raise HTTPException(409, f"Заказ в статусе «{order.status}» нельзя редактировать")

            item_id = await crm.add_order_item(
                order_id, body.product_id, body.quantity, body.unit_price,
            )
            await crm.recalculate_order_totals(order_id)

            return {"ok": True, "item_id": item_id}
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
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
        crm = await _get_crm()
        try:
            # Проверить что заказ доступен для редактирования
            try:
                order = await crm.get_order(order_id)
            except IntegramNotFoundError:
                raise HTTPException(404, "Заказ не найден")
            if order.status not in EDITABLE_STATUSES:
                raise HTTPException(409, f"Заказ в статусе «{order.status}» нельзя редактировать")

            # Получить текущую позицию для дефолтных значений
            items = await crm.get_order_items(order_id)
            current = next((i for i in items if i.id == item_id), None)
            if not current:
                raise HTTPException(404, "Позиция не найдена")

            qty = body.quantity if body.quantity is not None else current.quantity
            price = body.unit_price if body.unit_price is not None else current.unit_price

            await crm.update_order_item(item_id, qty=qty, price=price)
            await crm.recalculate_order_totals(order_id)

            return {"ok": True, "item_id": item_id}
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
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
        crm = await _get_crm()
        try:
            # Проверить что заказ доступен для редактирования
            try:
                order = await crm.get_order(order_id)
            except IntegramNotFoundError:
                raise HTTPException(404, "Заказ не найден")
            if order.status not in EDITABLE_STATUSES:
                raise HTTPException(409, f"Заказ в статусе «{order.status}» нельзя редактировать")

            await crm.delete_order_item(item_id)
            await crm.recalculate_order_totals(order_id)

            return {"ok": True, "item_id": item_id}
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


# ---------------------------------------------------------------------------
# Клиенты
# ---------------------------------------------------------------------------

@app.get("/api/clients", tags=["clients"])
async def list_clients(
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = _DEFAULT_PAGE_SIZE,
    _: CurrentUser = Depends(_require_role("admin")),
) -> dict[str, Any]:
    """Список клиентов с пагинацией и поиском."""
    try:
        crm = await _get_crm()
        try:
            clients = await crm.get_clients()
            result = [_client_to_dict(c) for c in clients]
            return _paginate(
                result, page, per_page, search,
                search_fields=["name", "phone", "address", "city", "telegram_username"],
            )
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(status_code=502, detail="Ошибка CRM")


@app.get("/api/clients/{client_id}", tags=["clients"])
async def get_client(
    client_id: int,
    _: CurrentUser = Depends(_require_role("admin")),
) -> dict[str, Any]:
    """Клиент + история заказов."""
    try:
        crm = await _get_crm()
        try:
            clients = await crm.get_clients()
            client = next((c for c in clients if c.id == client_id), None)
            if not client:
                raise HTTPException(status_code=404, detail="Клиент не найден")

            orders = await crm.get_orders(client_id=client_id)
            result = _client_to_dict(client)
            result["orders"] = [_order_to_dict(o) for o in orders]
            return result
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(status_code=502, detail="Ошибка CRM")


# ---------------------------------------------------------------------------
# Товары
# ---------------------------------------------------------------------------

@app.get("/api/products", tags=["products"])
async def list_products(
    in_stock_only: bool = False,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = _DEFAULT_PAGE_SIZE,
    _: CurrentUser = Depends(_require_role("admin", "warehouse")),
) -> dict[str, Any]:
    """Список товаров с пагинацией и поиском."""
    try:
        crm = await _get_crm()
        try:
            products = await crm.get_products(in_stock_only=in_stock_only)
            result = [_product_to_dict(p) for p in products]
            return _paginate(
                result, page, per_page, search,
                search_fields=["name", "category", "description", "sku_uds"],
            )
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(status_code=502, detail="Ошибка CRM")


@app.post("/api/products", tags=["products"])
async def create_product(
    body: ProductCreate,
    _: CurrentUser = Depends(_require_role("admin")),
) -> dict:
    """Создать товар."""
    try:
        crm = await _get_crm()
        try:
            product_id = await crm.create_product(
                body.name,
                price=body.price,
                weight=body.weight,
                description=body.description,
                in_stock=body.in_stock,
                sku_uds=body.sku_uds,
                category=body.category,
                short_name=body.short_name,
                stock=body.stock,
            )
            return {"ok": True, "product_id": product_id}
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
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
        crm = await _get_crm()
        try:
            kwargs = body.model_dump(exclude_none=True)
            if kwargs:
                await crm.update_product(product_id, **kwargs)
            return {"ok": True, "product_id": product_id}
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


@app.delete("/api/products/{product_id}", tags=["products"])
async def delete_product(
    product_id: int,
    _: CurrentUser = Depends(_require_role("admin")),
) -> dict:
    """Снять товар с продажи (in_stock = false)."""
    try:
        crm = await _get_crm()
        try:
            await crm.delete_product(product_id)
            return {"ok": True, "product_id": product_id}
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
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
        crm = await _get_crm()
        try:
            await crm.update_product_stock(product_id, body.stock)
            return {"ok": True, "product_id": product_id, "stock": body.stock}
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


# ---------------------------------------------------------------------------
# Экспорт CSV
# ---------------------------------------------------------------------------

def _to_csv(rows: list[dict], fields: list[str], headers: list[str]) -> str:
    """Сгенерировать CSV-строку из списка словарей."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row.get(f, "") for f in fields])
    return buf.getvalue()


@app.get("/api/export/orders", tags=["export"])
async def export_orders_csv(
    status: Optional[str] = None,
    _: CurrentUser = Depends(_require_role("admin")),
) -> StreamingResponse:
    """Экспорт заказов в CSV."""
    try:
        crm = await _get_crm()
        try:
            orders = await crm.get_orders(status=status)
            rows = [_order_to_dict(o) for o in orders]
            content = _to_csv(
                rows,
                fields=["number", "date", "client_name", "status", "delivery_method",
                         "delivery_address", "items_total", "delivery_cost", "total", "source"],
                headers=["Номер", "Дата", "Клиент", "Статус", "Доставка",
                          "Адрес", "Сумма товаров", "Доставка ₽", "Итого", "Источник"],
            )
            return StreamingResponse(
                io.BytesIO(content.encode("utf-8-sig")),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": "attachment; filename=orders.csv"},
            )
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


@app.get("/api/export/clients", tags=["export"])
async def export_clients_csv(
    _: CurrentUser = Depends(_require_role("admin")),
) -> StreamingResponse:
    """Экспорт клиентов в CSV."""
    try:
        crm = await _get_crm()
        try:
            clients = await crm.get_clients()
            rows = [_client_to_dict(c) for c in clients]
            content = _to_csv(
                rows,
                fields=["id", "name", "phone", "city", "address", "source", "telegram_username"],
                headers=["ID", "ФИО", "Телефон", "Город", "Адрес", "Источник", "Telegram"],
            )
            return StreamingResponse(
                io.BytesIO(content.encode("utf-8-sig")),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": "attachment; filename=clients.csv"},
            )
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


@app.get("/api/export/products", tags=["export"])
async def export_products_csv(
    _: CurrentUser = Depends(_require_role("admin")),
) -> StreamingResponse:
    """Экспорт товаров в CSV."""
    try:
        crm = await _get_crm()
        try:
            products = await crm.get_products(in_stock_only=False)
            rows = [_product_to_dict(p) for p in products]
            content = _to_csv(
                rows,
                fields=["id", "name", "category", "price", "weight", "stock", "in_stock"],
                headers=["ID", "Название", "Категория", "Цена", "Вес", "Остаток", "В наличии"],
            )
            return StreamingResponse(
                io.BytesIO(content.encode("utf-8-sig")),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": "attachment; filename=products.csv"},
            )
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


# ---------------------------------------------------------------------------
# Пользователи (только admin) — делегация в web/users.py через crm.api
# ---------------------------------------------------------------------------

@app.get("/api/users", tags=["users"])
async def list_users(
    _: CurrentUser = Depends(_require_role("admin")),
) -> list[dict[str, Any]]:
    """Список всех пользователей."""
    try:
        crm = await _get_crm()
        try:
            return await get_all_users(crm.api)
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
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
        crm = await _get_crm()
        try:
            user_id = await create_user(
                crm.api,
                username=body.username,
                password=body.password,
                role=body.role,
                display_name=body.display_name,
            )
            return {"ok": True, "user_id": user_id}
        finally:
            await crm.close()
    except ValueError as e:
        raise HTTPException(400, str(e))
    except (IntegramError, IntegramAPIError) as exc:
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
        crm = await _get_crm()
        try:
            await update_user_service(
                crm.api,
                user_id,
                password=body.password,
                role=body.role,
                display_name=body.display_name,
                active=body.active,
            )
            return {"ok": True, "user_id": user_id}
        finally:
            await crm.close()
    except ValueError as e:
        raise HTTPException(400, str(e))
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


@app.delete("/api/users/{user_id}", tags=["users"])
async def delete_user_endpoint(
    user_id: int,
    _: CurrentUser = Depends(_require_role("admin")),
) -> dict:
    """Деактивировать пользователя."""
    try:
        crm = await _get_crm()
        try:
            await delete_user_service(crm.api, user_id)
            return {"ok": True, "user_id": user_id}
        finally:
            await crm.close()
    except (IntegramError, IntegramAPIError) as exc:
        logger.error("Ошибка Integram: %s", exc)
        raise HTTPException(502, "Ошибка CRM")


# ---------------------------------------------------------------------------
# SSE — серверные уведомления (Server-Sent Events)
# ---------------------------------------------------------------------------

# Очередь событий для подписчиков
_event_subscribers: list[asyncio.Queue] = []


async def push_event(event_type: str, data: dict) -> None:
    """Отправить событие всем подписанным SSE-клиентам."""
    payload = {"type": event_type, **data}
    dead: list[asyncio.Queue] = []
    for q in _event_subscribers:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _event_subscribers.remove(q)


@app.get("/api/events", tags=["events"])
async def sse_events(
    token: Optional[str] = None,
):
    """SSE-поток событий (новые заказы, смена статусов, трек-номера).

    Принимает JWT-токен через заголовок Authorization: Bearer <token>
    или query-параметр ?token=<token> (для EventSource в браузере).
    """
    # EventSource не поддерживает заголовки — принимаем токен из query param
    if token:
        try:
            payload = jwt.decode(token, _WEB_SECRET, algorithms=[_ALGORITHM])
            role = payload.get("role", "")
            if role not in ("admin", "warehouse"):
                raise HTTPException(status_code=403, detail="Недостаточно прав")
        except JWTError:
            raise HTTPException(status_code=401, detail="Неверный токен")
    else:
        raise HTTPException(status_code=401, detail="Токен не передан")

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _event_subscribers.append(queue)

    async def event_stream():
        try:
            while True:
                event = await queue.get()
                yield f"data: {json_lib.dumps(event, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in _event_subscribers:
                _event_subscribers.remove(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/internal/push-event", tags=["internal"], include_in_schema=False)
async def internal_push_event(request: Request, body: dict) -> dict:
    """Внутренний эндпоинт: бот-контейнер → SSE-подписчики веб-панели.

    Защищён заголовком X-Internal-Secret (env: WEB_INTERNAL_SECRET).
    Если секрет не задан — эндпоинт отключён (403).
    """
    if not _INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Внутренний эндпоинт отключён")
    secret = request.headers.get("X-Internal-Secret", "")
    if secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Неверный секрет")
    event_type = body.pop("type", "unknown")
    await push_event(event_type, body)
    return {"ok": True}
