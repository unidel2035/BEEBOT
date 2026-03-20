"""Агент «Осмотр улья» — диагностический диалог.

Ведёт пошаговый диалог для уточнения запроса здоровья:
  1. Клиент описывает проблему или цель
  2. Агент задаёт 1–2 уточняющих вопроса (через LLM)
  3. На основе всех ответов: поиск в базе знаний + персонализированная рекомендация

Максимум 2 уточняющих вопроса. Клиент может пропустить шаги кнопкой «Получить рекомендацию».
"""

from __future__ import annotations

import logging

from aiogram.fsm.state import State, StatesGroup

from src.knowledge_base import KnowledgeBase
from src.llm_client import LLMClient, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FSM состояния
# ---------------------------------------------------------------------------

INSPECT_TIMEOUT_SECONDS = 10 * 60  # 10 минут


class InspectFSM(StatesGroup):
    """3 состояния диагностического диалога."""
    describing_issue = State()   # 1. Клиент описывает проблему
    answering_q1     = State()   # 2. Ответ на 1-й уточняющий вопрос
    answering_q2     = State()   # 3. Ответ на 2-й уточняющий вопрос


# ---------------------------------------------------------------------------
# Системные промпты
# ---------------------------------------------------------------------------

_QUESTION_SYSTEM = (
    "Ты — Александр Дмитров, пчеловод и консультант по здоровью. "
    "Клиент описал тебе свою проблему или цель. "
    "Задай ОДИН короткий уточняющий вопрос, чтобы дать точную рекомендацию. "
    "Вопрос должен касаться: возраста/пола, длительности проблемы, "
    "аллергий или противопоказаний, или уточнения симптомов. "
    "Задавай вопросы на русском языке. Только ОДИН вопрос, коротко."
)

_RECOMMENDATION_SYSTEM = (
    SYSTEM_PROMPT
    + "\n\nСейчас ты проводишь персональную консультацию. "
    "У тебя есть история вопросов клиента. "
    "Дай конкретную, персонализированную рекомендацию: "
    "какой продукт или программу использовать, дозировка, курс. "
    "Опирайся строго на контекст из базы знаний."
)


# ---------------------------------------------------------------------------
# Агент
# ---------------------------------------------------------------------------

class InspectorAgent:
    """Диагностический агент — анализирует запрос и выдаёт рекомендацию."""

    def __init__(self, kb: KnowledgeBase | None = None):
        self.llm = LLMClient()
        self.kb = kb  # разделяемый экземпляр из BeebotAgent

    # ------------------------------------------------------------------
    # Генерация уточняющего вопроса
    # ------------------------------------------------------------------

    def generate_question(self, collected: list[str]) -> str:
        """Сгенерировать уточняющий вопрос на основе собранной информации.

        Args:
            collected: Список ответов клиента (issue + предыдущие ответы).
        """
        dialogue = "\n".join(f"Клиент: {msg}" for msg in collected)
        try:
            resp = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=[
                    {"role": "system", "content": _QUESTION_SYSTEM},
                    {"role": "user", "content": dialogue},
                ],
                max_tokens=120,
                temperature=0.5,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error("InspectorAgent generate_question error: %s", e)
            return "Расскажи подробнее — как давно это беспокоит и есть ли аллергии?"

    # ------------------------------------------------------------------
    # Финальная рекомендация
    # ------------------------------------------------------------------

    def generate_recommendation(
        self,
        collected: list[str],
        style: str | None = None,
    ) -> str:
        """Сгенерировать персональную рекомендацию.

        Args:
            collected: Все ответы клиента (issue + уточнения).
            style: Стиль «Голос Улья» (опционально).
        """
        if self.kb is None or not self.kb.chunks:
            return (
                "База знаний пока недоступна — задай вопрос напрямую, "
                "я отвечу как смогу."
            )

        # Объединить все ответы в один запрос для KB
        combined_query = " ".join(collected)
        chunks = self.kb.search(combined_query, top_k=5)

        # Формируем контекст
        context_parts = [
            f"[Источник: {c.get('source', '?')}]\n{c['text']}"
            for c in chunks
        ]
        context_text = "\n\n---\n\n".join(context_parts)

        dialogue_text = "\n".join(
            f"{'Проблема' if i == 0 else f'Уточнение {i}'}: {msg}"
            for i, msg in enumerate(collected)
        )

        user_prompt = (
            f"Контекст из базы знаний:\n\n{context_text}\n\n"
            f"---\n\n"
            f"Диалог с клиентом:\n{dialogue_text}\n\n"
            "Дай персонализированную рекомендацию на основе этой информации."
        )

        from src.llm_client import VOICE_STYLES
        system = _RECOMMENDATION_SYSTEM
        if style and style in VOICE_STYLES:
            system += "\n\nСтиль ответа: " + VOICE_STYLES[style]["prompt_suffix"]

        try:
            resp = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=600,
                temperature=0.4,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error("InspectorAgent generate_recommendation error: %s", e)
            return "Не удалось сформировать рекомендацию. Попробуй задать вопрос напрямую."
