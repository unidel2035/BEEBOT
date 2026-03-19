"""Telegram-уведомления клиентам при изменении статуса заказа.

Используется напрямую через Telegram Bot API (httpx), без aiogram,
чтобы работать из контейнера веб-панели.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_BEEKEEPER_CHAT_ID = os.getenv("BEEKEEPER_CHAT_ID", "")
_TG_API = "https://api.telegram.org"


# Шаблоны сообщений по статусам
STATUS_MESSAGES = {
    "Подтверждён": (
        "✅ Ваш заказ *#{number}* подтверждён!\n"
        "Начинаем сборку. Александр свяжется с вами перед отправкой."
    ),
    "В сборке": (
        "📦 Ваш заказ *#{number}* собирается!\n"
        "Скоро отправим."
    ),
    "Отправлен": (
        "🚚 Ваш заказ *#{number}* отправлен!\n"
        "{tracking}"
        "Ожидайте доставку."
    ),
    "Доставлен": (
        "🎉 Ваш заказ *#{number}* доставлен!\n"
        "Спасибо за покупку! Будем рады видеть вас снова."
    ),
    "Отменён": (
        "❌ Ваш заказ *#{number}* отменён.\n"
        "Если есть вопросы — напишите нам."
    ),
}


async def notify_client_status_change(
    telegram_id: int,
    order_number: str,
    new_status: str,
    tracking_number: Optional[str] = None,
) -> bool:
    """Отправить уведомление клиенту о смене статуса заказа.

    Returns:
        True если сообщение отправлено, False если нет.
    """
    if not _BOT_TOKEN or not telegram_id:
        return False

    template = STATUS_MESSAGES.get(new_status)
    if not template:
        return False

    tracking = ""
    if tracking_number and new_status == "Отправлен":
        tracking = f"Трек-номер: `{tracking_number}`\n"

    text = template.format(number=order_number, tracking=tracking)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_TG_API}/bot{_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": telegram_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )
            if resp.status_code == 200:
                logger.info(
                    "Уведомление отправлено клиенту %d: заказ %s → %s",
                    telegram_id, order_number, new_status,
                )
                return True
            else:
                logger.warning(
                    "Не удалось отправить уведомление клиенту %d: %s",
                    telegram_id, resp.text,
                )
                return False
    except Exception as e:
        logger.error("Ошибка отправки уведомления: %s", e)
        return False


_BEEKEEPER_STATUS_MESSAGES = {
    "Подтверждён": "✅ Заказ *#{number}* подтверждён",
    "В сборке": "📦 Заказ *#{number}* в сборке",
    "Отправлен": "🚚 Заказ *#{number}* отправлен{tracking}",
    "Доставлен": "🎉 Заказ *#{number}* доставлен",
    "Отменён": "❌ Заказ *#{number}* отменён",
}


async def notify_beekeeper_status_change(
    order_number: str,
    new_status: str,
    client_name: str = "",
    tracking_number: Optional[str] = None,
) -> bool:
    """Уведомить пчеловода о смене статуса заказа (из веб-панели)."""
    if not _BOT_TOKEN or not _BEEKEEPER_CHAT_ID:
        return False

    template = _BEEKEEPER_STATUS_MESSAGES.get(new_status)
    if not template:
        return False

    tracking = f"\nТрек: `{tracking_number}`" if tracking_number and new_status == "Отправлен" else ""
    text = template.format(number=order_number, tracking=tracking)
    if client_name:
        text += f"\nКлиент: {client_name}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_TG_API}/bot{_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": int(_BEEKEEPER_CHAT_ID),
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )
            if resp.status_code == 200:
                logger.info("Уведомление пчеловоду: заказ %s → %s", order_number, new_status)
                return True
            logger.warning("Не удалось уведомить пчеловода: %s", resp.text)
            return False
    except Exception as e:
        logger.error("Ошибка уведомления пчеловоду: %s", e)
        return False


async def notify_client_tracking(
    telegram_id: int,
    order_number: str,
    tracking_number: str,
) -> bool:
    """Отправить клиенту трек-номер."""
    if not _BOT_TOKEN or not telegram_id:
        return False

    text = (
        f"📬 Трек-номер вашего заказа *#{order_number}*:\n"
        f"`{tracking_number}`\n"
        f"Отслеживайте доставку!"
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_TG_API}/bot{_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": telegram_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )
            return resp.status_code == 200
    except Exception as e:
        logger.error("Ошибка отправки трек-номера: %s", e)
        return False
