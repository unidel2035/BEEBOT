"""Агент «Ассистент пчеловода» — прямой LLM-диалог с CRM-контекстом.

Активируется командой /admin для ADMIN_CHAT_ID.
Получает текущие данные CRM и отвечает как персональный бизнес-ассистент.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_SYSTEM = """Ты — личный ассистент пчеловода Александра Дмитрова, владельца «Усадьба Дмитровых».

Текущее состояние бизнеса (данные из CRM):
{crm_context}

Сегодня: {today}

Ты умеешь:
- Анализировать заказы, продажи, клиентов
- Отвечать на вопросы по статистике CRM
- Составлять тексты: ответы клиентам, посты, объявления
- Давать советы по развитию бизнеса
- Обсуждать любые вопросы

Правила:
- Отвечай только на русском языке
- Данные CRM выше — это АКТУАЛЬНЫЙ снимок, используй их напрямую
- НЕ говори что у тебя "нет доступа к CRM" — данные уже есть в контексте
- Если конкретной информации нет в снимке — скажи «в снимке этих данных нет»
- Отвечай кратко и по делу
"""


class AdminChatAgent:
    """Персональный ассистент для ADMIN_CHAT_ID с доступом к данным CRM."""

    def __init__(self, groq_client=None, model: str = "", crm=None):
        self._groq = groq_client
        self._model = model
        self._crm = crm
        # История диалога: user_id → [{role, content}, ...]
        self._history: dict[int, list[dict]] = {}

    def set_crm(self, crm) -> None:
        self._crm = crm

    async def _get_crm_context(self) -> str:
        """Собрать снимок состояния CRM в виде текста для системного промпта."""
        if not self._crm:
            return "CRM не подключена."

        lines = []

        # Заказы
        try:
            orders = await self._crm.get_orders()
            active = [o for o in orders if o.status in ("Новый", "Подтверждён", "В сборке")]
            revenue_total = sum((o.total or 0) for o in orders)
            lines.append(f"ЗАКАЗЫ: {len(orders)} всего, {len(active)} активных, выручка {revenue_total:,.0f} ₽")

            # Последние 10 с датой
            if orders:
                lines.append("Последние 10 заказов (номер | дата | статус | сумма):")
                for o in reversed(orders[-10:]):
                    try:
                        date_str = o.date.strftime("%d.%m.%Y") if o.date else "—"
                    except Exception:
                        date_str = str(o.date)[:10] if o.date else "—"
                    lines.append(f"  #{o.number} | {date_str} | {o.status} | {o.total or 0:.0f} ₽")
        except Exception as e:
            lines.append(f"Ошибка загрузки заказов: {e}")

        # Товары / склад
        try:
            products = await self._crm.get_products()
            low = [p for p in products if p.stock is not None and p.stock < 5]
            lines.append(f"ТОВАРЫ: {len(products)} позиций")
            if low:
                lines.append("Мало на складе (<5 шт.):")
                for p in low[:7]:
                    lines.append(f"  {p.name}: {p.stock} шт.")
        except Exception as e:
            lines.append(f"Ошибка загрузки товаров: {e}")

        # Клиенты
        try:
            clients = await self._crm.get_clients()
            lines.append(f"КЛИЕНТЫ: {len(clients)} в базе")
        except Exception as e:
            lines.append(f"Ошибка загрузки клиентов: {e}")

        return "\n".join(lines)

    def _call_llm(self, messages: list[dict]) -> str:
        """Синхронный вызов Groq (совместим с существующим LLMClient)."""
        for attempt in range(3):
            try:
                resp = self._groq.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=1000,
                    temperature=0.6,
                )
                return resp.choices[0].message.content
            except Exception as e:
                logger.error("AdminChat LLM error (attempt %d/3): %s", attempt + 1, e)
                if attempt < 2:
                    time.sleep(2 ** attempt)
        return "⚠️ Не удалось получить ответ. Попробуй ещё раз."

    async def chat(self, user_id: int, message: str) -> str:
        """Обработать сообщение пчеловода и вернуть ответ."""
        if not self._groq:
            return "⚠️ LLM не настроен. Проверь GROQ_API_KEY в .env"

        crm_context = await self._get_crm_context()
        system = _SYSTEM.format(
            crm_context=crm_context,
            today=datetime.now().strftime("%d.%m.%Y"),
        )

        history = self._history.get(user_id, [])
        messages = [{"role": "system", "content": system}] + history + [
            {"role": "user", "content": message},
        ]

        answer = await asyncio.to_thread(self._call_llm, messages)

        # Обновить историю (хранить последние 10 пар)
        updated = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": answer},
        ]
        self._history[user_id] = updated[-20:]

        return answer

    def clear_history(self, user_id: int) -> None:
        """Очистить историю диалога пользователя."""
        self._history.pop(user_id, None)
