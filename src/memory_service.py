"""MemoryService — единый API памяти для всех агентов (M.4).

Скрывает детали хранилища (UserMemory/SQLite) за чистым интерфейсом.
Агенты работают с MemoryService, не зная об устройстве БД.

Возможности:
  - Факты о пользователе (здоровье, интересы) с namespace по agent_id
  - Автоизвлечение фактов из текста (extract_fact)
  - Эпизоды взаимодействий (история консультаций, заказов)
  - Сводный контекст пользователя для передачи в LLM

Использование:
    svc = get_memory_service()
    svc.save_fact_from_text(user_id, text, agent_id="beebot")
    ctx = svc.get_user_context(user_id, agent_id="beebot")
    # ctx = {"facts": [...], "episodes": [...]}
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.memory import UserMemory, extract_fact

logger = logging.getLogger(__name__)

# Путь к БД по умолчанию (переопределяется в тестах через конструктор)
_DEFAULT_DB_PATH = Path("data/memory.db")


class MemoryService:
    """Единый API памяти для агентов.

    Оборачивает UserMemory и предоставляет высокоуровневые операции.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._memory = UserMemory(db_path or _DEFAULT_DB_PATH)

    # ------------------------------------------------------------------
    # Facts
    # ------------------------------------------------------------------

    def get_facts(self, user_id: int, agent_id: str | None = None) -> list[str]:
        """Факты о пользователе. agent_id=None — все агенты."""
        return self._memory.get_facts(user_id, agent_id=agent_id)

    def add_fact(
        self,
        user_id: int,
        fact: str,
        category: str = "general",
        source: str = "auto",
        agent_id: str = "global",
    ) -> bool:
        """Добавить факт. Возвращает True если добавлен (не дубль)."""
        return self._memory.add_fact(
            user_id, fact, category=category, source=source, agent_id=agent_id
        )

    def save_fact_from_text(
        self,
        user_id: int,
        text: str,
        agent_id: str = "global",
    ) -> bool:
        """Автоматически извлечь факт из текста и сохранить.

        Возвращает True если факт обнаружен и добавлен (не дубль).
        """
        extracted = extract_fact(text)
        if extracted is None:
            return False
        fact_text, category = extracted
        added = self._memory.add_fact(
            user_id, fact_text, category=category, source="auto", agent_id=agent_id
        )
        if added:
            logger.info(
                "MemoryService: сохранён факт user=%d [%s/%s]: %.60s",
                user_id, category, agent_id, fact_text,
            )
        return added

    # ------------------------------------------------------------------
    # Episodes
    # ------------------------------------------------------------------

    def add_episode(
        self,
        user_id: int,
        agent_id: str,
        event_type: str,
        summary: str,
        detail: str | None = None,
    ) -> int:
        """Сохранить эпизод взаимодействия. Возвращает id записи."""
        return self._memory.add_episode(
            user_id=user_id,
            agent_id=agent_id,
            event_type=event_type,
            summary=summary,
            detail=detail,
        )

    def get_episodes(
        self,
        user_id: int,
        agent_id: str | None = None,
        event_type: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Эпизоды пользователя (свежие первыми).

        Args:
            agent_id:   фильтр по агенту. None — все агенты.
            event_type: фильтр по типу события. None — все типы.
            limit:      максимальное количество записей.
        """
        return self._memory.get_episodes(
            user_id=user_id,
            agent_id=agent_id,
            event_type=event_type,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Unified context
    # ------------------------------------------------------------------

    def get_user_context(
        self,
        user_id: int,
        agent_id: str | None = None,
        max_facts: int = 10,
        max_episodes: int = 5,
    ) -> dict:
        """Сводный контекст пользователя для передачи агенту.

        Returns:
            {"facts": list[str], "episodes": list[dict]}
        """
        facts = self.get_facts(user_id, agent_id=agent_id)[:max_facts]
        episodes = self.get_episodes(user_id, agent_id=agent_id, limit=max_episodes)
        return {"facts": facts, "episodes": episodes}


# ---------------------------------------------------------------------------
# Глобальный синглтон
# ---------------------------------------------------------------------------

_memory_service: MemoryService | None = None


def get_memory_service() -> MemoryService:
    """Вернуть глобальный экземпляр MemoryService (ленивая инициализация)."""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service
