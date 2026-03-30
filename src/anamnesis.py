"""AnamnesisCache — эпизодическая память пользователя (A3 Gift Ontology).

Агрегирует прошлые значимые взаимодействия из SQLite (факты о здоровье/интересах)
и CrmAgent (история заказов). GiftBroker включает anamnesis[] в каждый Gift —
агент получает контекст истории без дополнительных запросов к БД.

Использование персонализации (10.3):
    anamnesis = await cache.get(user_id, crm_agent)
    hint = cache.format_for_llm(anamnesis)
    # hint → «Прошлые заказы: #42 — Доставлен, 2800 ₽; ...»
    # Добавляется в memory_facts консультанта
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.crm_agent import CrmAgent
    from src.memory import UserMemory

logger = logging.getLogger(__name__)


class AnamnesisCache:
    """Кэш значимых прошлых взаимодействий на user_id."""

    def __init__(self, memory: "UserMemory") -> None:
        self._memory = memory

    async def get(
        self,
        user_id: int,
        crm_agent: "CrmAgent | None" = None,
    ) -> list[dict]:
        """Собрать анамнез: факты из SQLite + история заказов из CRM.

        Returns:
            list[dict] со структурой: {"type": str, "text": str, ...}
            type: "memory" | "order"
        """
        result: list[dict] = []

        # 1. Факты о здоровье/интересах из SQLite (долгосрочная память)
        try:
            facts = self._memory.get_facts(user_id)
            for fact in facts[:10]:
                result.append({"type": "memory", "text": fact})
        except Exception as e:
            logger.warning("AnamnesisCache: ошибка чтения SQLite: %s", e)

        # 2. История заказов из CRM (персонализация «Вы уже брали»)
        if crm_agent and crm_agent.available:
            try:
                orders = await crm_agent.get_orders_for_user(user_id)
                for order in orders[-5:]:  # последние 5 заказов
                    total_hint = f", {order.total:.0f} ₽" if order.total else ""
                    status = order.status or ""
                    result.append({
                        "type": "order",
                        "text": f"Заказ #{order.number or order.id} — {status}{total_hint}",
                        "order_id": order.id,
                        "status": status,
                    })
            except Exception as e:
                logger.warning("AnamnesisCache: ошибка загрузки заказов из CRM: %s", e)

        return result

    def format_for_llm(self, anamnesis: list[dict]) -> str | None:
        """Преобразовать анамнез в строку для добавления в LLM-контекст.

        Returns:
            None если анамнез пустой, иначе строку с фактами и историей.
        """
        if not anamnesis:
            return None

        memory_items = [a["text"] for a in anamnesis if a["type"] == "memory"]
        order_items = [a["text"] for a in anamnesis if a["type"] == "order"]

        parts: list[str] = []
        if memory_items:
            parts.append("Что знаем о пользователе: " + "; ".join(memory_items[:5]))
        if order_items:
            parts.append("Прошлые заказы: " + "; ".join(order_items[:3]))

        return "\n".join(parts) if parts else None
