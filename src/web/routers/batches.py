"""Роутер партий отправки."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.integram_api import IntegramAPIError
from src.integram_client import IntegramError
from src.web.deps import CurrentUser, _get_crm, _paginate

logger = logging.getLogger(__name__)
router = APIRouter()


class BatchCreate(BaseModel):
    date: str              # "DD.MM.YYYY"
    delivery_method: Optional[str] = ""
    note: Optional[str] = ""


class BatchOrderAssign(BaseModel):
    batch_id: Optional[int] = None   # None — снять партию


@router.get("/api/batches")
async def list_batches(
    page: int = 1,
    per_page: int = 50,
    user: CurrentUser = Depends(),
):
    """Список партий отправки с количеством заказов."""
    async with _get_crm() as crm:
        batches = await crm.get_batches()
        # Подтягиваем кол-во заказов из данных заказов
        orders = await crm._api.get_orders()
        counts: dict[int, int] = {}
        for o in orders:
            bid = o.get("batch_id")
            if bid:
                counts[bid] = counts.get(bid, 0) + 1
        for b in batches:
            b["order_count"] = counts.get(b["id"], b.get("count", 0))
    return _paginate(batches, page, per_page)


@router.post("/api/batches", status_code=201)
async def create_batch(
    body: BatchCreate,
    user: CurrentUser = Depends(),
):
    """Создать новую партию отправки."""
    try:
        try:
            date = datetime.strptime(body.date, "%d.%m.%Y")
        except ValueError:
            date = datetime.strptime(body.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="Неверный формат даты (ожидается DD.MM.YYYY)")

    async with _get_crm() as crm:
        try:
            batch_id = await crm.create_batch(
                date=date,
                delivery_method=body.delivery_method or "",
                note=body.note or "",
            )
        except (IntegramError, IntegramAPIError) as e:
            raise HTTPException(status_code=502, detail=str(e))
    return {"id": batch_id, "date": body.date, "delivery_method": body.delivery_method}


@router.patch("/api/orders/{order_id}/batch")
async def assign_batch(
    order_id: int,
    body: BatchOrderAssign,
    user: CurrentUser = Depends(),
):
    """Назначить / снять партию для заказа."""
    async with _get_crm() as crm:
        try:
            await crm.set_order_batch(order_id, body.batch_id)
            if body.batch_id:
                await crm.update_batch_count(body.batch_id)
        except (IntegramError, IntegramAPIError) as e:
            raise HTTPException(status_code=502, detail=str(e))
    return {"ok": True, "order_id": order_id, "batch_id": body.batch_id}


@router.get("/api/batches/{batch_id}/orders")
async def batch_orders(
    batch_id: int,
    user: CurrentUser = Depends(),
):
    """Заказы, входящие в партию."""
    async with _get_crm() as crm:
        all_orders = await crm._api.get_orders()
        orders = [o for o in all_orders if o.get("batch_id") == batch_id]
    return {"items": orders, "total": len(orders)}
