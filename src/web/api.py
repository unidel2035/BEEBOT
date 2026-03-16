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
    REQ_ORDER_STATUS,
    REQ_ORDER_TRACKING,
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
    """Получить заказ по ID."""
    try:
        integram = await _get_integram()
        try:
            orders = await integram.get_orders()
            for o in orders:
                if o["id"] == order_id:
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


class StatusUpdate(BaseModel):
    status: str


class TrackingUpdate(BaseModel):
    tracking_number: str


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
