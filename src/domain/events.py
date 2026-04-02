"""Доменные события — типизированные сообщения между слоями.

Используются в EventBus и NotificationService.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True)
class OrderCreated:
    """Заказ создан."""
    order_id: int
    order_number: str
    client_id: int
    client_name: str
    total: float
    source: str
    items: list[dict] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class OrderStatusChanged:
    """Статус заказа изменился."""
    order_id: int
    order_number: str
    old_status: str
    new_status: str
    client_id: int
    client_name: str
    tracking_number: Optional[str] = None
    comment: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class DeliveryUpdate:
    """Обновление статуса доставки (от трекера)."""
    order_id: int
    order_number: str
    tracking_number: str
    tracking_status: str
    provider: str  # СДЭК / Почта России
    client_tg_id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class NewOrderFromUDS:
    """Новый заказ из UDS-магазина."""
    uds_order_id: int
    order_number: str
    client_name: str
    total: float
    items_count: int
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class TunnelStatusChanged:
    """SSH-туннель изменил состояние."""
    is_healthy: bool
    port: int
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class BackupCompleted:
    """Бэкап выполнен."""
    backup_type: str  # daily / weekly
    path: str
    size_bytes: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
