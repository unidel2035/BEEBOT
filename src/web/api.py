"""FastAPI-бэкенд веб-панели управления заказами «Усадьба Дмитровых».

Эндпоинты:
  POST /api/auth/token          — получить JWT по логину/паролю
  GET  /api/dashboard           — статистика (новые заказы, выручка за день/неделю)
  GET  /api/orders              — список заказов (фильтр по статусу, клиенту)
  GET  /api/orders/{id}         — заказ по ID
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

from src.integram_api import IntegramAPI, IntegramAPIError

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
