"""FastAPI-бэкенд веб-панели управления заказами «Усадьба Дмитровых».

Эндпоинты:
  POST /api/auth/token          — получить JWT по логину/паролю
  GET  /api/dashboard           — статистика (новые заказы, выручка за день/неделю)
  GET  /api/orders              — список заказов (фильтр по статусу, клиенту)
  GET  /api/orders/{id}         — заказ по ID
  POST /api/orders              — создать заказ вручную
  PATCH /api/orders/{id}/status — сменить статус заказа
  PATCH /api/orders/{id}/tracking — задать трек-номер
  GET  /api/clients             — список клиентов
  GET  /api/clients/{id}        — клиент + история заказов
  GET  /api/products            — список товаров (CRUD)
  POST /api/products            — создать товар
  PATCH /api/products/{id}      — обновить товар
  DELETE /api/products/{id}     — удалить товар (снять с продажи)

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

from src.integram_client import IntegramClient, IntegramError, IntegramNotFoundError
from src.crm_schema import ORDER_STATUSES, DELIVERY_METHODS

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
    allow_origins=["*"],  # В продакшене заменить на конкретный домен
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


class DashboardStats(BaseModel):
    new_orders_today: int
    new_orders_week: int
    revenue_today: float
    revenue_week: float
    total_orders: int
    total_clients: int


class OrderStatusUpdate(BaseModel):
    status: str


class OrderTrackingUpdate(BaseModel):
    tracking_number: str


class ManualOrderItem(BaseModel):
    product_id: int
    quantity: int
    unit_price: float


class ManualOrderCreate(BaseModel):
    client_name: str
    phone: Optional[str] = None
    delivery_method: Optional[str] = None
    delivery_address: Optional[str] = None
    delivery_cost: Optional[float] = None
    items: list[ManualOrderItem]
    note: Optional[str] = None


class ProductCreate(BaseModel):
    name: str
    category: Optional[str] = None
    price: Optional[float] = None
    weight: Optional[float] = None
    description: Optional[str] = None
    in_stock: bool = True
    sku_uds: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    weight: Optional[float] = None
    description: Optional[str] = None
    in_stock: Optional[bool] = None
    sku_uds: Optional[str] = None


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
# Хелпер: создать аутентифицированный IntegramClient
# ---------------------------------------------------------------------------

async def _get_integram() -> IntegramClient:
    client = IntegramClient()
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

@app.get("/api/reference", response_model=ReferenceData, tags=["reference"])
async def get_reference(
    _: str = Depends(_get_current_user),
) -> ReferenceData:
    """Получить справочные данные: статусы заказов и способы доставки."""
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
            orders = await integram.get_orders()
            clients_set: set[int] = set()
            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=today_start.weekday())

            new_orders_today = 0
            new_orders_week = 0
            revenue_today = 0.0
            revenue_week = 0.0

            for order in orders:
                clients_set.add(order.client_id)
                order_date = order.date
                # Приводим к UTC для сравнения
                if order_date.tzinfo is None:
                    order_date = order_date.replace(tzinfo=timezone.utc)
                amount = order.total or 0.0
                if order_date >= today_start:
                    if order.status == "Новый":
                        new_orders_today += 1
                    revenue_today += amount
                if order_date >= week_start:
                    if order.status == "Новый":
                        new_orders_week += 1
                    revenue_week += amount

            return DashboardStats(
                new_orders_today=new_orders_today,
                new_orders_week=new_orders_week,
                revenue_today=revenue_today,
                revenue_week=revenue_week,
                total_orders=len(orders),
                total_clients=len(clients_set),
            )
        finally:
            await integram.close()
    except IntegramError as exc:
        logger.error("Ошибка Integram при загрузке дашборда: %s", exc)
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
    """Список заказов с фильтрацией по статусу и/или клиенту."""
    try:
        integram = await _get_integram()
        try:
            orders = await integram.get_orders(client_id=client_id, status=status)
            return [o.model_dump(mode="json") for o in orders]
        finally:
            await integram.close()
    except IntegramError as exc:
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
            order = await integram.get_order(order_id)
            return order.model_dump(mode="json")
        finally:
            await integram.close()
    except IntegramNotFoundError:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    except IntegramError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка CRM: {exc}")


@app.post("/api/orders", status_code=201, tags=["orders"])
async def create_manual_order(
    body: ManualOrderCreate,
    _: str = Depends(_get_current_user),
) -> dict[str, Any]:
    """Создать заказ вручную (без Telegram-диалога)."""
    if body.delivery_method and body.delivery_method not in DELIVERY_METHODS:
        raise HTTPException(
            status_code=422,
            detail=f"Неизвестный способ доставки. Допустимые: {DELIVERY_METHODS}",
        )
    try:
        integram = await _get_integram()
        try:
            # Создать или найти клиента
            # Поиск по имени — упрощённо создаём нового клиента для ручного ввода
            client_data: dict[str, Any] = {"ФИО": body.client_name}
            if body.phone:
                client_data["Телефон"] = body.phone
            if body.delivery_address:
                client_data["Адрес"] = body.delivery_address
            client_data["Источник"] = "Ручной ввод"

            raw_client = await integram._request("POST", "/api/clients", json=client_data)
            client_id: int = raw_client.get("id", 0)

            items = [
                {
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                }
                for item in body.items
            ]
            items_total = sum(i.quantity * i.unit_price for i in body.items)
            delivery_cost = body.delivery_cost or 0.0

            order = await integram.create_order(
                client_id=client_id,
                items=items,
                delivery_method=body.delivery_method,
                delivery_address=body.delivery_address,
                delivery_cost=delivery_cost,
                items_total=items_total,
                total=items_total + delivery_cost,
                source="Ручной ввод",
            )
            return order.model_dump(mode="json")
        finally:
            await integram.close()
    except IntegramError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка CRM: {exc}")


@app.patch("/api/orders/{order_id}/status", tags=["orders"])
async def update_order_status(
    order_id: int,
    body: OrderStatusUpdate,
    _: str = Depends(_get_current_user),
) -> dict[str, str]:
    """Сменить статус заказа."""
    if body.status not in ORDER_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Неизвестный статус. Допустимые: {ORDER_STATUSES}",
        )
    try:
        integram = await _get_integram()
        try:
            await integram.update_order_status(order_id, body.status)
            return {"ok": "true", "status": body.status}
        finally:
            await integram.close()
    except IntegramNotFoundError:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    except IntegramError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка CRM: {exc}")


@app.patch("/api/orders/{order_id}/tracking", tags=["orders"])
async def update_order_tracking(
    order_id: int,
    body: OrderTrackingUpdate,
    _: str = Depends(_get_current_user),
) -> dict[str, str]:
    """Задать трек-номер отправления."""
    try:
        integram = await _get_integram()
        try:
            await integram._request(
                "PATCH",
                f"/api/orders/{order_id}",
                json={"Трек-номер": body.tracking_number},
            )
            return {"ok": "true", "tracking_number": body.tracking_number}
        finally:
            await integram.close()
    except IntegramNotFoundError:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    except IntegramError as exc:
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
            data = await integram._request("GET", "/api/clients")
            items = data if isinstance(data, list) else data.get("items", data.get("data", []))
            clients = [integram._parse_client(item) for item in items]
            return [c.model_dump(mode="json") for c in clients]
        finally:
            await integram.close()
    except IntegramError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка CRM: {exc}")


@app.get("/api/clients/{client_id}", tags=["clients"])
async def get_client(
    client_id: int,
    _: str = Depends(_get_current_user),
) -> dict[str, Any]:
    """Получить клиента и его историю заказов."""
    try:
        integram = await _get_integram()
        try:
            data = await integram._request("GET", f"/api/clients/{client_id}")
            client = integram._parse_client(data)
            orders = await integram.get_orders(client_id=client_id)
            result = client.model_dump(mode="json")
            result["orders"] = [o.model_dump(mode="json") for o in orders]
            return result
        finally:
            await integram.close()
    except IntegramNotFoundError:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    except IntegramError as exc:
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
            products = await integram.get_products(in_stock_only=in_stock_only)
            return [p.model_dump(mode="json") for p in products]
        finally:
            await integram.close()
    except IntegramError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка CRM: {exc}")


@app.post("/api/products", status_code=201, tags=["products"])
async def create_product(
    body: ProductCreate,
    _: str = Depends(_get_current_user),
) -> dict[str, Any]:
    """Создать новый товар в каталоге."""
    try:
        integram = await _get_integram()
        try:
            product_data: dict[str, Any] = {
                "Название": body.name,
                "В наличии": body.in_stock,
            }
            if body.category:
                product_data["Категория"] = body.category
            if body.price is not None:
                product_data["Цена"] = body.price
            if body.weight is not None:
                product_data["Вес"] = body.weight
            if body.description:
                product_data["Описание"] = body.description
            if body.sku_uds:
                product_data["Артикул UDS"] = body.sku_uds

            raw = await integram._request("POST", "/api/products", json=product_data)
            product = integram._parse_product(raw)
            return product.model_dump(mode="json")
        finally:
            await integram.close()
    except IntegramError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка CRM: {exc}")


@app.patch("/api/products/{product_id}", tags=["products"])
async def update_product(
    product_id: int,
    body: ProductUpdate,
    _: str = Depends(_get_current_user),
) -> dict[str, Any]:
    """Обновить товар (название, цену, наличие и т.д.)."""
    try:
        integram = await _get_integram()
        try:
            update_data: dict[str, Any] = {}
            field_map = {
                "name": "Название",
                "category": "Категория",
                "price": "Цена",
                "weight": "Вес",
                "description": "Описание",
                "in_stock": "В наличии",
                "sku_uds": "Артикул UDS",
            }
            for py_key, api_key in field_map.items():
                val = getattr(body, py_key)
                if val is not None:
                    update_data[api_key] = val

            raw = await integram._request(
                "PATCH", f"/api/products/{product_id}", json=update_data
            )
            product = integram._parse_product(raw)
            return product.model_dump(mode="json")
        finally:
            await integram.close()
    except IntegramNotFoundError:
        raise HTTPException(status_code=404, detail="Товар не найден")
    except IntegramError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка CRM: {exc}")


@app.delete("/api/products/{product_id}", tags=["products"])
async def delete_product(
    product_id: int,
    _: str = Depends(_get_current_user),
) -> dict[str, str]:
    """Снять товар с продажи (установить «В наличии» = false)."""
    try:
        integram = await _get_integram()
        try:
            await integram._request(
                "PATCH",
                f"/api/products/{product_id}",
                json={"В наличии": False},
            )
            return {"ok": "true", "product_id": str(product_id)}
        finally:
            await integram.close()
    except IntegramNotFoundError:
        raise HTTPException(status_code=404, detail="Товар не найден")
    except IntegramError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка CRM: {exc}")
