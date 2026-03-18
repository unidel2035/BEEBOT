"""Фоновый авто-трекинг отправленных заказов.

Периодически проверяет статус доставки по трек-номеру.
При обнаружении доставки — обновляет статус в CRM и уведомляет клиента.

Использование:
    tracker = OrderTracker(crm, notifier)
    task = asyncio.create_task(tracker.run())  # запустить фоновый цикл
    ...
    tracker.stop()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.delivery.calculator import DeliveryCalculator

logger = logging.getLogger(__name__)

# Интервал проверки: 2 часа
CHECK_INTERVAL = 2 * 60 * 60

# Статусы СДЭК, означающие доставку
_CDEK_DELIVERED_CODES = {"DELIVERED", "4"}
_CDEK_DELIVERED_NAMES = {"вручен", "доставлен", "получен"}

# Статусы Почты России, означающие доставку
_POCHTA_DELIVERED_NAMES = {"вручение", "получение"}


def _is_delivered(track_result: dict, provider: str) -> bool:
    """Определить, доставлено ли отправление по данным трекинга."""
    status = (track_result.get("status") or "").lower()
    code = (track_result.get("code") or "").upper()

    if provider == "СДЭК":
        return code in _CDEK_DELIVERED_CODES or any(w in status for w in _CDEK_DELIVERED_NAMES)
    if provider == "Почта России":
        return any(w in status for w in _POCHTA_DELIVERED_NAMES)
    return False


class OrderTracker:
    """Фоновый сервис автотрекинга."""

    def __init__(self, crm, notify_fn=None):
        """
        Args:
            crm: IntegramClient для чтения/обновления заказов.
            notify_fn: async callable(telegram_id, order_number, new_status)
                       для уведомления клиента. Если None — уведомления отключены.
        """
        self._crm = crm
        self._notify_fn = notify_fn
        self._calc = DeliveryCalculator()
        self._running = False

    async def run(self) -> None:
        """Запустить бесконечный цикл проверки."""
        self._running = True
        logger.info("Авто-трекинг запущен (интервал %d сек)", CHECK_INTERVAL)
        while self._running:
            try:
                await self._check_all()
            except Exception as e:
                logger.error("Ошибка авто-трекинга: %s", e)
            await asyncio.sleep(CHECK_INTERVAL)

    def stop(self) -> None:
        """Остановить цикл."""
        self._running = False
        logger.info("Авто-трекинг остановлен")

    async def _check_all(self) -> None:
        """Проверить все отправленные заказы с трек-номерами."""
        orders = await self._crm.get_orders(status="Отправлен")
        shipped = [o for o in orders if o.tracking_number]
        if not shipped:
            return

        logger.info("Авто-трекинг: проверяю %d отправленных заказов", len(shipped))

        for order in shipped:
            await self._check_one(order)
            await asyncio.sleep(2)  # не перегружать API

    async def _check_one(self, order) -> None:
        """Проверить один заказ."""
        provider = order.delivery_method or "СДЭК"
        try:
            result = await self._calc.track(order.tracking_number, provider_name=provider)
        except ValueError:
            # Провайдер не поддерживается — пропустить
            return

        if _is_delivered({"status": result.status, "code": getattr(result, "code", "")}, provider):
            logger.info(
                "Заказ #%s доставлен (трек %s, %s)",
                order.number, order.tracking_number, provider,
            )
            try:
                await self._crm.update_order_status(order.id, "Доставлен")
            except Exception as e:
                logger.error("Не удалось обновить статус заказа #%s: %s", order.number, e)
                return

            # Уведомить клиента
            if self._notify_fn and order.client_id:
                try:
                    tg_id = await self._crm.get_client_telegram_id(order.client_id)
                    if tg_id:
                        await self._notify_fn(tg_id, order.number, "Доставлен")
                except Exception as e:
                    logger.warning("Не удалось уведомить клиента о доставке заказа #%s: %s", order.number, e)
