"""CrmAgent — единственный владелец CRM-домена.

Все вызовы к Integram должны идти через CrmAgent, а не напрямую через IntegramClient.
Это централизует логику повторных попыток, упрощает тестирование и аудит.

Использование:
    crm = CrmAgent(integram_client)          # в prod
    crm = CrmAgent()                         # без CRM (все методы возвращают пустые данные)

Примечание:
    Полная миграция всех 10+ прямых вызовов IntegramClient выполняется постепенно.
    На первом этапе CrmAgent используется оркестратором (health-факты) и AnamnesisCache.
"""
from __future__ import annotations

import logging
from typing import Optional

from src.models import Client, Order, Product

logger = logging.getLogger(__name__)


class CrmAgent:
    """Единственный владелец CRM-домена. Все вызовы к Integram — только через него."""

    def __init__(self, client=None) -> None:
        # client: Optional[IntegramClient] — передаётся из bot.py после init
        self._client = client

    @property
    def available(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------------
    # Клиенты
    # ------------------------------------------------------------------

    async def get_client_by_telegram_id(self, telegram_id: int) -> Optional[Client]:
        """Найти клиента по Telegram ID."""
        if not self._client:
            return None
        try:
            clients = await self._client.get_clients()
            return next((c for c in clients if c.telegram_id == telegram_id), None)
        except Exception as e:
            logger.warning("CrmAgent.get_client_by_telegram_id: %s", e)
            return None

    # ------------------------------------------------------------------
    # Заказы
    # ------------------------------------------------------------------

    async def get_orders_for_user(self, telegram_id: int) -> list[Order]:
        """Получить заказы пользователя по Telegram ID.

        Используется AnamnesisCache и персонализацией «Вы уже брали».
        """
        if not self._client:
            return []
        try:
            client = await self.get_client_by_telegram_id(telegram_id)
            if not client:
                return []
            orders = await self._client.get_orders(client_id=None)
            return [o for o in orders if o.client_id == client.id]
        except Exception as e:
            logger.warning("CrmAgent.get_orders_for_user: %s", e)
            return []

    async def get_products(self) -> list[Product]:
        """Получить список товаров из CRM."""
        if not self._client:
            return []
        try:
            return await self._client.get_products()
        except Exception as e:
            logger.warning("CrmAgent.get_products: %s", e)
            return []

    # ------------------------------------------------------------------
    # Профиль здоровья
    # ------------------------------------------------------------------

    async def add_health_fact(self, telegram_id: int, fact: str) -> None:
        """Дублировать health-факт в профиль здоровья Integram.

        Тихо игнорирует ошибки — основной факт уже сохранён в SQLite.
        """
        if not self._client or telegram_id <= 0:
            return
        try:
            await self._client.add_health_profile(telegram_id, fact)
        except Exception as e:
            logger.debug("CrmAgent.add_health_fact: не удалось записать в Integram: %s", e)
