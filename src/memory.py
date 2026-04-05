"""Долгосрочная память пользователей — SQLite-хранилище.

Хранит факты о пользователях между сессиями:
  health   — здоровье (язва, диабет, аллергия и т.д.)
  interest — интересы к продуктам/темам
  general  — прочие факты

Жизненный цикл:
  1. Пользователь пишет «у меня язва» → оркестратор авто-сохраняет факт
  2. Следующий визит → ConsultantAgent загружает факты → передаёт в LLM-контекст
  3. Пчеловод: /remember <telegram_id> <факт> → ручное добавление

Хранится в data/memory.db на VPS (вне Docker-образа, если том подключён).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Автодетект упоминаний здоровья/интересов в тексте пользователя
# ---------------------------------------------------------------------------

_HEALTH_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'у меня (язва|гастрит|диабет|аллергия|гипертония|гипотония|астма|артрит|остеохондроз|онкология)', re.I), "health"),
    (re.compile(r'я (диабетик|аллергик|гипертоник|гипотоник)', re.I), "health"),
    (re.compile(r'страдаю (от )?(язвы|диабета|аллергии|гипертонии|астмы|артрита)', re.I), "health"),
    (re.compile(r'(беременна|беременность|кормлю грудью)', re.I), "health"),
    (re.compile(r'принимаю (прополис|пергу|гомогенат|подмор|пжвм|настойку)', re.I), "interest"),
    (re.compile(r'уже (пробовал|принимала?|использовал[аи]?) (прополис|пергу|гомогенат|подмор|пжвм)', re.I), "interest"),
]

# Паттерны отрицания — если совпадают в том же предложении, факт НЕ сохраняется.
# Решает проблему «у меня нет язвы» → не должно сохраняться как health-факт «язва».
_NEGATION_RE = re.compile(
    r'\b(нет|не|без|никогда|не было|не страдаю|не болею|не принимал[аи]?|не пробовал[аи]?|не использовал[аи]?)\b',
    re.I,
)


def extract_fact(text: str) -> tuple[str, str] | None:
    """Извлечь факт о пользователе из его сообщения.

    Пропускает предложения с отрицаниями — «у меня нет язвы» не сохраняется.

    Returns:
        (fact_text, category) или None если ничего не обнаружено.
    """
    for pattern, category in _HEALTH_PATTERNS:
        if not pattern.search(text):
            continue
        # Взять предложение с совпадением
        for sentence in re.split(r"[.!?\n]", text):
            s = sentence.strip()
            if not pattern.search(s) or not (8 <= len(s) <= 200):
                continue
            # Пропустить предложения с отрицаниями
            if _NEGATION_RE.search(s):
                continue
            return s, category
    return None


# ---------------------------------------------------------------------------
# Основной класс
# ---------------------------------------------------------------------------


class UserMemory:
    """SQLite-хранилище долгосрочной памяти пользователей."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_memory (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    fact        TEXT    NOT NULL,
                    category    TEXT    NOT NULL DEFAULT 'general',
                    source      TEXT    NOT NULL DEFAULT 'auto',
                    agent_id    TEXT    NOT NULL DEFAULT 'global',
                    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tg_id ON user_memory(telegram_id)"
            )
            # Миграция: добавить agent_id если отсутствует (старая БД)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(user_memory)")}
            if "agent_id" not in cols:
                conn.execute(
                    "ALTER TABLE user_memory ADD COLUMN agent_id TEXT NOT NULL DEFAULT 'global'"
                )
            # M.3: таблица эпизодов (история взаимодействий агентов с пользователем)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    agent_id   TEXT    NOT NULL DEFAULT 'global',
                    event_type TEXT    NOT NULL,
                    summary    TEXT    NOT NULL,
                    detail     TEXT,
                    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ep_user_id ON episodes(user_id)"
            )

    def get_facts(self, telegram_id: int, agent_id: str | None = None) -> list[str]:
        """Вернуть факты о пользователе (последние 20, свежие сначала).

        Args:
            agent_id: фильтр по агенту. None — все агенты (backward compat).
        """
        with sqlite3.connect(self.db_path) as conn:
            if agent_id is None:
                rows = conn.execute(
                    "SELECT fact FROM user_memory "
                    "WHERE telegram_id = ? "
                    "ORDER BY created_at DESC LIMIT 20",
                    (telegram_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT fact FROM user_memory "
                    "WHERE telegram_id = ? AND agent_id = ? "
                    "ORDER BY created_at DESC LIMIT 20",
                    (telegram_id, agent_id),
                ).fetchall()
        return [row[0] for row in rows]

    def add_fact(
        self,
        telegram_id: int,
        fact: str,
        category: str = "general",
        source: str = "auto",
        agent_id: str = "global",
    ) -> bool:
        """Добавить факт. Возвращает True если добавлен (не дубль в рамках агента)."""
        fact = fact.strip()
        if not fact:
            return False
        with sqlite3.connect(self.db_path) as conn:
            exists = conn.execute(
                "SELECT id FROM user_memory WHERE telegram_id = ? AND fact = ? AND agent_id = ?",
                (telegram_id, fact, agent_id),
            ).fetchone()
            if exists:
                return False
            conn.execute(
                "INSERT INTO user_memory (telegram_id, fact, category, source, agent_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (telegram_id, fact, category, source, agent_id),
            )
        logger.info(
            "Memory: добавлен факт user=%d [%s/%s/%s]: %.60s",
            telegram_id, category, source, agent_id, fact,
        )
        return True

    def clear_facts(self, telegram_id: int) -> int:
        """Удалить все факты пользователя. Возвращает кол-во удалённых."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM user_memory WHERE telegram_id = ?",
                (telegram_id,),
            )
            return cur.rowcount

    def count_facts(self, telegram_id: int) -> int:
        """Количество сохранённых фактов о пользователе."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM user_memory WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # M.3: Episodes — история взаимодействий агентов с пользователем
    # ------------------------------------------------------------------

    def add_episode(
        self,
        user_id: int,
        agent_id: str,
        event_type: str,
        summary: str,
        detail: str | None = None,
    ) -> int:
        """Сохранить эпизод взаимодействия. Возвращает id новой записи."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO episodes (user_id, agent_id, event_type, summary, detail) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, agent_id, event_type, summary, detail),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_episodes(
        self,
        user_id: int,
        agent_id: str | None = None,
        event_type: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Вернуть эпизоды пользователя (свежие первыми).

        Args:
            agent_id:   фильтр по агенту. None — все агенты.
            event_type: фильтр по типу события. None — все типы.
            limit:      максимальное количество записей.
        """
        query = "SELECT id, user_id, agent_id, event_type, summary, detail, created_at FROM episodes WHERE user_id = ?"
        params: list = [user_id]
        if agent_id is not None:
            query += " AND agent_id = ?"
            params.append(agent_id)
        if event_type is not None:
            query += " AND event_type = ?"
            params.append(event_type)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row[0],
                "user_id": row[1],
                "agent_id": row[2],
                "event_type": row[3],
                "summary": row[4],
                "detail": row[5],
                "created_at": row[6],
            }
            for row in rows
        ]
