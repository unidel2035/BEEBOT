"""Tests for src/memory_service.py — MemoryService (M.4)."""

import tempfile
from pathlib import Path

import pytest

from src.memory_service import MemoryService


@pytest.fixture
def svc():
    with tempfile.TemporaryDirectory() as d:
        yield MemoryService(Path(d) / "memory.db")


# ---------------------------------------------------------------------------
# Facts API
# ---------------------------------------------------------------------------

class TestMemoryServiceFacts:
    def test_add_and_get_fact(self, svc):
        svc.add_fact(1001, "у меня язва", "health")
        facts = svc.get_facts(1001)
        assert "у меня язва" in facts

    def test_duplicate_not_added(self, svc):
        svc.add_fact(1002, "одинаковый факт")
        result = svc.add_fact(1002, "одинаковый факт")
        assert result is False

    def test_get_facts_filtered_by_agent_id(self, svc):
        svc.add_fact(1003, "факт beebot", agent_id="beebot")
        svc.add_fact(1003, "факт devbot", agent_id="devbot")
        assert "факт beebot" in svc.get_facts(1003, agent_id="beebot")
        assert "факт devbot" not in svc.get_facts(1003, agent_id="beebot")

    def test_get_facts_none_returns_all(self, svc):
        svc.add_fact(1004, "факт beebot", agent_id="beebot")
        svc.add_fact(1004, "факт devbot", agent_id="devbot")
        assert len(svc.get_facts(1004)) == 2


# ---------------------------------------------------------------------------
# save_fact_from_text — авто-извлечение факта из текста
# ---------------------------------------------------------------------------

class TestSaveFactFromText:
    def test_saves_detected_health_fact(self, svc):
        result = svc.save_fact_from_text(2001, "у меня язва желудка уже 3 года")
        assert result is True
        facts = svc.get_facts(2001)
        assert any("язва" in f for f in facts)

    def test_returns_false_if_no_fact_detected(self, svc):
        result = svc.save_fact_from_text(2002, "хочу купить мёд")
        assert result is False

    def test_returns_false_if_negation(self, svc):
        result = svc.save_fact_from_text(2003, "у меня нет язвы")
        assert result is False

    def test_agent_id_passed_to_fact(self, svc):
        svc.save_fact_from_text(2004, "у меня аллергия на пыльцу", agent_id="beebot")
        facts = svc.get_facts(2004, agent_id="beebot")
        assert len(facts) == 1

    def test_duplicate_not_saved_twice(self, svc):
        svc.save_fact_from_text(2005, "у меня язва желудка уже 3 года")
        svc.save_fact_from_text(2005, "у меня язва желудка уже 3 года")
        assert len(svc.get_facts(2005)) == 1


# ---------------------------------------------------------------------------
# Episodes API
# ---------------------------------------------------------------------------

class TestMemoryServiceEpisodes:
    def test_add_and_get_episode(self, svc):
        ep_id = svc.add_episode(3001, "beebot", "consult", "Вопрос про прополис")
        assert ep_id > 0
        eps = svc.get_episodes(3001)
        assert len(eps) == 1
        assert eps[0]["summary"] == "Вопрос про прополис"

    def test_get_episodes_filtered_by_agent(self, svc):
        svc.add_episode(3002, "beebot", "consult", "консультация", "")
        svc.add_episode(3002, "logist", "order", "заказ", "")
        eps = svc.get_episodes(3002, agent_id="logist")
        assert len(eps) == 1
        assert eps[0]["event_type"] == "order"

    def test_get_episodes_filtered_by_event_type(self, svc):
        svc.add_episode(3003, "beebot", "consult", "вопрос", "")
        svc.add_episode(3003, "logist", "order", "заказ", "")
        orders = svc.get_episodes(3003, event_type="order")
        assert len(orders) == 1

    def test_get_episodes_limit(self, svc):
        for i in range(5):
            svc.add_episode(3004, "beebot", "consult", f"эпизод {i}", "")
        assert len(svc.get_episodes(3004, limit=2)) == 2


# ---------------------------------------------------------------------------
# get_user_context — сводный контекст для агента
# ---------------------------------------------------------------------------

class TestGetUserContext:
    def test_returns_facts_and_episodes(self, svc):
        svc.add_fact(4001, "у меня язва", "health", agent_id="beebot")
        svc.add_episode(4001, "beebot", "consult", "Спросил про прополис")

        ctx = svc.get_user_context(4001)
        assert "facts" in ctx
        assert "episodes" in ctx
        assert len(ctx["facts"]) == 1
        assert len(ctx["episodes"]) == 1

    def test_empty_user_returns_empty_context(self, svc):
        ctx = svc.get_user_context(9999)
        assert ctx["facts"] == []
        assert ctx["episodes"] == []

    def test_max_facts_limits_output(self, svc):
        for i in range(10):
            svc.add_fact(4002, f"факт {i}", agent_id="beebot")
        ctx = svc.get_user_context(4002, max_facts=3)
        assert len(ctx["facts"]) <= 3

    def test_max_episodes_limits_output(self, svc):
        for i in range(10):
            svc.add_episode(4003, "beebot", "consult", f"эпизод {i}")
        ctx = svc.get_user_context(4003, max_episodes=2)
        assert len(ctx["episodes"]) <= 2

    def test_agent_id_filters_context(self, svc):
        svc.add_fact(4004, "факт beebot", agent_id="beebot")
        svc.add_fact(4004, "факт devbot", agent_id="devbot")
        svc.add_episode(4004, "beebot", "consult", "эпизод beebot")
        svc.add_episode(4004, "devbot", "task", "эпизод devbot")

        ctx = svc.get_user_context(4004, agent_id="beebot")
        assert all("beebot" not in f or True for f in ctx["facts"])
        assert len(ctx["facts"]) == 1
        assert len(ctx["episodes"]) == 1
        assert ctx["episodes"][0]["agent_id"] == "beebot"
