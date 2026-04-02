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
                    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tg_id ON user_memory(telegram_id)"
            )

    def get_facts(self, telegram_id: int) -> list[str]:
        """Вернуть все факты о пользователе (последние 20, свежие сначала)."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT fact FROM user_memory "
                "WHERE telegram_id = ? "
                "ORDER BY created_at DESC LIMIT 20",
                (telegram_id,),
            ).fetchall()
        return [row[0] for row in rows]

    def add_fact(
        self,
        telegram_id: int,
        fact: str,
        category: str = "general",
        source: str = "auto",
    ) -> bool:
        """Добавить факт. Возвращает True если добавлен (не дубль)."""
        fact = fact.strip()
        if not fact:
            return False
        with sqlite3.connect(self.db_path) as conn:
            exists = conn.execute(
                "SELECT id FROM user_memory WHERE telegram_id = ? AND fact = ?",
                (telegram_id, fact),
            ).fetchone()
            if exists:
                return False
            conn.execute(
                "INSERT INTO user_memory (telegram_id, fact, category, source) "
                "VALUES (?, ?, ?, ?)",
                (telegram_id, fact, category, source),
            )
        logger.info(
            "Memory: добавлен факт user=%d [%s/%s]: %.60s",
            telegram_id, category, source, fact,
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
