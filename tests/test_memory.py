"""Tests for src/memory.py — UserMemory with agent_id namespace (M.2)."""

import tempfile
from pathlib import Path

import pytest

from src.memory import UserMemory, extract_fact


# ---------------------------------------------------------------------------
# extract_fact
# ---------------------------------------------------------------------------

class TestExtractFact:
    def test_detects_health_fact(self):
        result = extract_fact("у меня язва желудка уже 3 года")
        assert result is not None
        fact, category = result
        assert category == "health"
        assert "язва" in fact

    def test_detects_interest_fact(self):
        result = extract_fact("я уже принимаю прополис каждое утро")
        assert result is not None
        _, category = result
        assert category == "interest"

    def test_negation_skipped(self):
        result = extract_fact("у меня нет язвы")
        assert result is None

    def test_no_match_returns_none(self):
        result = extract_fact("хочу купить прополис")
        assert result is None

    def test_negation_in_same_sentence_skipped(self):
        result = extract_fact("я не диабетик")
        assert result is None


# ---------------------------------------------------------------------------
# UserMemory — базовые операции
# ---------------------------------------------------------------------------

@pytest.fixture
def mem():
    with tempfile.TemporaryDirectory() as d:
        yield UserMemory(Path(d) / "memory.db")


class TestUserMemoryBasic:
    def test_add_and_get_fact(self, mem):
        mem.add_fact(1001, "у меня язва", "health")
        facts = mem.get_facts(1001)
        assert "у меня язва" in facts

    def test_duplicate_not_added(self, mem):
        mem.add_fact(1001, "одинаковый факт")
        mem.add_fact(1001, "одинаковый факт")
        assert mem.count_facts(1001) == 1

    def test_empty_fact_rejected(self, mem):
        result = mem.add_fact(1001, "   ")
        assert result is False

    def test_clear_facts(self, mem):
        mem.add_fact(1001, "факт 1")
        mem.add_fact(1001, "факт 2")
        removed = mem.clear_facts(1001)
        assert removed == 2
        assert mem.count_facts(1001) == 0

    def test_isolation_between_users(self, mem):
        mem.add_fact(1001, "факт пользователя 1")
        mem.add_fact(1002, "факт пользователя 2")
        assert mem.get_facts(1001) == ["факт пользователя 1"]
        assert mem.get_facts(1002) == ["факт пользователя 2"]


# ---------------------------------------------------------------------------
# M.2: agent_id namespace
# ---------------------------------------------------------------------------

class TestAgentIdNamespace:
    def test_add_fact_with_agent_id(self, mem):
        """add_fact должен принимать параметр agent_id."""
        result = mem.add_fact(2001, "у меня язва", "health", agent_id="beebot")
        assert result is True

    def test_get_facts_filtered_by_agent_id(self, mem):
        """get_facts(user_id, agent_id='beebot') должен вернуть только факты beebot."""
        mem.add_fact(2002, "факт beebot", agent_id="beebot")
        mem.add_fact(2002, "факт devbot", agent_id="devbot")

        beebot_facts = mem.get_facts(2002, agent_id="beebot")
        assert "факт beebot" in beebot_facts
        assert "факт devbot" not in beebot_facts

    def test_get_facts_none_returns_all_agents(self, mem):
        """get_facts(user_id, agent_id=None) должен вернуть факты всех агентов."""
        mem.add_fact(2003, "факт beebot", agent_id="beebot")
        mem.add_fact(2003, "факт devbot", agent_id="devbot")

        all_facts = mem.get_facts(2003, agent_id=None)
        assert "факт beebot" in all_facts
        assert "факт devbot" in all_facts

    def test_get_facts_backward_compat_no_agent_id(self, mem):
        """get_facts(user_id) без agent_id должен вернуть все факты (backward compat)."""
        mem.add_fact(2004, "факт beebot", agent_id="beebot")
        mem.add_fact(2004, "факт global", agent_id="global")

        all_facts = mem.get_facts(2004)
        assert len(all_facts) == 2

    def test_add_fact_default_agent_id_is_global(self, mem):
        """add_fact без agent_id должен сохранять с agent_id='global'."""
        mem.add_fact(2005, "факт без агента")
        # Факт должен быть виден при запросе agent_id='global'
        global_facts = mem.get_facts(2005, agent_id="global")
        assert "факт без агента" in global_facts

    def test_duplicate_same_agent(self, mem):
        """Дубликат в рамках одного агента не добавляется."""
        mem.add_fact(2006, "факт", agent_id="beebot")
        result = mem.add_fact(2006, "факт", agent_id="beebot")
        assert result is False
        assert mem.count_facts(2006) == 1

    def test_same_fact_different_agents_both_stored(self, mem):
        """Один и тот же текст для разных агентов — хранятся оба."""
        mem.add_fact(2007, "общий факт", agent_id="beebot")
        result = mem.add_fact(2007, "общий факт", agent_id="devbot")
        assert result is True
        assert mem.count_facts(2007) == 2

    def test_get_facts_unknown_agent_returns_empty(self, mem):
        """get_facts с несуществующим agent_id возвращает пустой список."""
        mem.add_fact(2008, "факт beebot", agent_id="beebot")
        facts = mem.get_facts(2008, agent_id="unknown_agent")
        assert facts == []

    def test_migration_existing_db(self):
        """База без колонки agent_id должна мигрировать автоматически."""
        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "old_memory.db"
            # Создать базу без agent_id (старая схема)
            import sqlite3
            with sqlite3.connect(db_path) as conn:
                conn.execute("""
                    CREATE TABLE user_memory (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER NOT NULL,
                        fact        TEXT    NOT NULL,
                        category    TEXT    NOT NULL DEFAULT 'general',
                        source      TEXT    NOT NULL DEFAULT 'auto',
                        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
                    )
                """)
                conn.execute(
                    "INSERT INTO user_memory (telegram_id, fact) VALUES (3001, 'старый факт')"
                )

            # Открыть с новым UserMemory — должна мигрировать без ошибок
            mem = UserMemory(db_path)
            facts = mem.get_facts(3001)
            assert "старый факт" in facts
            # Старые записи должны получить agent_id='global' по умолчанию
            global_facts = mem.get_facts(3001, agent_id="global")
            assert "старый факт" in global_facts
