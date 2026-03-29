"""Агент работника склада — режим сборки заказов в Telegram-боте.

Интерфейс полностью кнопочный (без текстового ввода):
  - Очередь заказов к сборке (статус Новый/Подтверждён)
  - Карточка заказа с составом
  - Чеклист позиций (inline toggle)
  - Смена статуса: Новый/Подтверждён → В сборке → уведомление пчеловода

Push-уведомления при новом заказе — через notify_workers_new_order() из notifications.py.
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

if TYPE_CHECKING:
    from src.integram_client import IntegramClient
    from src.models import Order, OrderItem

logger = logging.getLogger(__name__)

# Статусы, которые показывает очередь
WORKER_QUEUE_STATUSES = {"Новый", "Подтверждён", "В сборке"}

# In-memory чеклист: {(worker_chat_id, order_id): set[item_id]}
_checked: dict[tuple[int, int], set[int]] = {}


# ---------------------------------------------------------------------------
# CRM-операции
# ---------------------------------------------------------------------------

async def get_worker_queue(crm: "IntegramClient") -> list["Order"]:
    """Заказы со статусом Новый/Подтверждён/В сборке."""
    all_orders = await crm.get_orders()
    return [o for o in all_orders if o.status in WORKER_QUEUE_STATUSES]


# ---------------------------------------------------------------------------
# Клавиатуры
# ---------------------------------------------------------------------------

def build_queue_keyboard(orders: list["Order"]) -> InlineKeyboardMarkup:
    """Список заказов + кнопка обновить."""
    rows = []
    for o in orders:
        status_icon = "🔄" if o.status == "В сборке" else "📋"
        total_str = f"{o.total:.0f} ₽" if o.total else "—"
        label = f"{status_icon} #{o.number} · {o.client_name or f'Клиент #{o.client_id}'} · {total_str}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"worker:order:{o.id}")])
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="worker:queue")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_order_keyboard(
    order_id: int,
    items: list["OrderItem"],
    worker_chat_id: int,
    status: str,
) -> InlineKeyboardMarkup:
    """Клавиатура карточки заказа: чеклист + действие + назад."""
    rows = []
    checked = _checked.get((worker_chat_id, order_id), set())

    if status in ("Новый", "Подтверждён"):
        # Ещё не взят — показать состав и кнопку «Взять в работу»
        rows.append([InlineKeyboardButton(
            text="✅ Взять в работу",
            callback_data=f"worker:take:{order_id}",
        )])
    else:
        # В сборке — чеклист позиций
        for item in items:
            is_checked = item.id in checked
            mark = "✅" if is_checked else "☐"
            name = item.product_name or f"Товар #{item.product_id}"
            label = f"{mark} {name} × {item.quantity} шт"
            rows.append([InlineKeyboardButton(
                text=label,
                callback_data=f"worker:check:{order_id}:{item.id}",
            )])

        # Кнопка «Собран» появляется только когда все позиции отмечены
        all_item_ids = {item.id for item in items}
        if all_item_ids and all_item_ids.issubset(checked):
            rows.append([InlineKeyboardButton(
                text="📦 Заказ собран — готов к отправке!",
                callback_data=f"worker:done:{order_id}",
            )])

    rows.append([InlineKeyboardButton(text="← Очередь", callback_data="worker:queue")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# Форматирование текста
# ---------------------------------------------------------------------------

def format_queue_text(orders: list["Order"]) -> str:
    """Текст сообщения с очередью заказов."""
    if not orders:
        return "✅ Очередь пуста — нет заказов к сборке."
    new_count = sum(1 for o in orders if o.status in ("Новый", "Подтверждён"))
    in_progress = sum(1 for o in orders if o.status == "В сборке")
    parts = []
    if new_count:
        parts.append(f"{new_count} к сборке")
    if in_progress:
        parts.append(f"{in_progress} в работе")
    summary = " · ".join(parts)
    return f"📦 *Очередь сборки* — {summary}\n\nВыберите заказ:"


def format_order_card(
    order: "Order",
    items: list["OrderItem"],
    worker_chat_id: int,
) -> str:
    """Текст карточки заказа."""
    checked = _checked.get((worker_chat_id, order.id), set())
    status_icons = {
        "Новый": "🔵",
        "Подтверждён": "🟡",
        "В сборке": "🔄",
    }
    icon = status_icons.get(order.status, "📋")
    client = order.client_name or f"Клиент #{order.client_id}"
    total_str = f"{order.total:.0f} ₽" if order.total else "—"

    lines = [
        f"📋 *Заказ #{order.number}*",
        f"Статус: {icon} {order.status}",
        "",
        f"👤 {client}",
    ]
    if order.delivery_method:
        lines.append(f"🚚 {order.delivery_method}")
    if order.delivery_address:
        lines.append(f"🏠 {order.delivery_address}")
    lines.append(f"💰 {total_str}")

    if items:
        lines.append("")
        if order.status in ("Новый", "Подтверждён"):
            lines.append(f"📦 *Состав ({len(items)} поз.):*")
            for item in items:
                name = item.product_name or f"Товар #{item.product_id}"
                lines.append(f"  • {name} × {item.quantity} шт")
        else:
            done = len(checked & {i.id for i in items})
            total_items = len(items)
            lines.append(f"📦 *Отмечайте по мере сборки* ({done}/{total_items}):")
    elif order.status in ("Новый", "Подтверждён"):
        lines.append("")
        lines.append("📦 *Состав:* позиции загружаются...")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Управление чеклистом
# ---------------------------------------------------------------------------

def toggle_item(worker_chat_id: int, order_id: int, item_id: int) -> None:
    """Отметить/снять позицию в чеклисте."""
    key = (worker_chat_id, order_id)
    if key not in _checked:
        _checked[key] = set()
    if item_id in _checked[key]:
        _checked[key].discard(item_id)
    else:
        _checked[key].add(item_id)


def clear_checklist(worker_chat_id: int, order_id: int) -> None:
    """Очистить чеклист (после завершения сборки)."""
    _checked.pop((worker_chat_id, order_id), None)


def is_fully_checked(worker_chat_id: int, order_id: int, items: list["OrderItem"]) -> bool:
    """Все ли позиции отмечены."""
    if not items:
        return False
    checked = _checked.get((worker_chat_id, order_id), set())
    return {i.id for i in items}.issubset(checked)
