"""NotificationService — единая точка отправки уведомлений.

Объединяет:
- src/notifications.py (Notifier — бот → пчеловод/клиент/работники)
- src/web/notifications.py (HTTP → Telegram API)

Не знает про aiogram или FastAPI. Работает через callback-функции.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine, Optional

from src.models import Order

logger = logging.getLogger(__name__)

# Тип: async функция отправки сообщения в Telegram
TelegramSender = Callable[[int, str], Coroutine[Any, Any, bool]]


class NotificationService:
    """Отправка уведомлений клиентам, пчеловоду и работникам склада."""

    def __init__(
        self,
        *,
        send_telegram: Optional[TelegramSender] = None,
        beekeeper_chat_id: Optional[int] = None,
        group_ids: frozenset[int] = frozenset(),
        worker_ids: frozenset[int] = frozenset(),
        get_client_tg_id: Optional[Callable] = None,
    ):
        self._send = send_telegram
        self._beekeeper_id = beekeeper_chat_id
        self._group_ids = group_ids
        self._worker_ids = worker_ids
        self._get_client_tg_id = get_client_tg_id

    # ------------------------------------------------------------------
    # События заказа
    # ------------------------------------------------------------------

    async def on_order_created(self, order: Order, items: list[dict]) -> None:
        """Новый заказ создан."""
        items_str = ", ".join(
            f"{i.get('quantity', 1)}×{i.get('product_name', '?')}" for i in items
        )
        total = order.total or 0

        # Пчеловоду
        text = (
            f"🆕 Новый заказ {order.number}\n"
            f"📦 {items_str}\n"
            f"💰 {total:.0f} ₽\n"
            f"📍 {order.source or 'неизвестно'}"
        )
        await self._send_to_beekeeper(text)

        # Работникам склада
        worker_text = f"📦 Новый заказ {order.number} — {total:.0f} ₽"
        await self._send_to_workers(worker_text)

    async def on_status_changed(
        self, order: Order, old_status: str, new_status: str,
    ) -> None:
        """Статус заказа изменился."""
        # Клиенту
        if order.client_id and self._get_client_tg_id:
            try:
                tg_id = await self._get_client_tg_id(order.client_id)
                if tg_id:
                    text = self._client_status_text(order, new_status)
                    await self._send_message(tg_id, text)
            except Exception as e:
                logger.warning("Уведомление клиенту: %s", e)

        # Пчеловоду
        text = (
            f"📋 {order.number}: {old_status or '—'} → {new_status}\n"
            f"👤 {order.client_name or '—'}"
        )
        await self._send_to_beekeeper(text)

    async def on_tracking_added(self, order: Order, tracking: str) -> None:
        """Трек-номер добавлен."""
        if order.client_id and self._get_client_tg_id:
            try:
                tg_id = await self._get_client_tg_id(order.client_id)
                if tg_id:
                    text = (
                        f"🚚 Заказ {order.number} отправлен!\n"
                        f"Трек-номер: {tracking}"
                    )
                    await self._send_message(tg_id, text)
            except Exception as e:
                logger.warning("Уведомление о трекинге: %s", e)

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    async def _send_message(self, chat_id: int, text: str) -> bool:
        """Отправить сообщение в Telegram."""
        if not self._send:
            return False
        try:
            return await self._send(chat_id, text)
        except Exception as e:
            logger.warning("Ошибка отправки в %d: %s", chat_id, e)
            return False

    async def _send_to_beekeeper(self, text: str) -> None:
        """Отправить пчеловоду + в группы."""
        if self._beekeeper_id:
            await self._send_message(self._beekeeper_id, text)
        for gid in self._group_ids:
            await self._send_message(gid, text)

    async def _send_to_workers(self, text: str) -> None:
        """Отправить работникам склада."""
        for wid in self._worker_ids:
            await self._send_message(wid, text)

    @staticmethod
    def _client_status_text(order: Order, status: str) -> str:
        """Текст уведомления клиенту о смене статуса."""
        tracking = ""
        if status == "Отправлен" and order.tracking_number:
            tracking = f"\nТрек-номер: {order.tracking_number}"

        templates = {
            "Подтверждён": f"✅ Заказ {order.number} подтверждён! Готовим к отправке.",
            "В сборке": f"📦 Заказ {order.number} собирается на пасеке.",
            "Отправлен": f"🚚 Заказ {order.number} отправлен!{tracking}",
            "Доставлен": f"✅ Заказ {order.number} доставлен! Спасибо за покупку!",
            "Отменён": f"❌ Заказ {order.number} отменён.",
        }
        return templates.get(status, f"📋 Заказ {order.number}: {status}")
