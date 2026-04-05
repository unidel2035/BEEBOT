"""Unit tests for src/orchestrator.py — intent classification and routing."""

import time
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from src.orchestrator import (
    Orchestrator,
    _classify_intent,
    _DIALOG_TTL_SECONDS,
    OrchestratorState,
)


def _make_orchestrator_with_memory() -> "Orchestrator":
    """Создать Orchestrator с MemorySaver (быстро, без aiosqlite) для unit-тестов."""
    with (
        patch("src.orchestrator.Groq"),
        patch("src.orchestrator.BeebotAgent"),
        patch("src.orchestrator.AnalystAgent"),
        patch("src.orchestrator.OntologyCache"),
    ):
        orch = Orchestrator()
    # Подменяем lazy-init: сразу вставляем MemorySaver и собираем граф
    orch._checkpointer = MemorySaver()
    orch._graph = orch._build_graph()
    # Настраиваем ontology mock: возвращать None (нет совпадений)
    orch._ontology.match.return_value = None
    orch._ontology.loaded = True
    orch._ontology.get_advice_prompt.return_value = None
    return orch


# ---------------------------------------------------------------------------
# _classify_intent
# ---------------------------------------------------------------------------

class TestClassifyIntent:
    """Tests for the _classify_intent helper."""

    def _make_groq_response(self, content: str):
        response = MagicMock()
        response.choices[0].message.content = content
        return response

    def test_returns_consult_for_product_question(self):
        client = MagicMock()
        client.chat.completions.create.return_value = self._make_groq_response("consult")
        result = _classify_intent(client, "llama-3.3-70b-versatile", "Как принимать прополис?")
        assert result == "consult"

    def test_returns_order_for_buy_intent(self):
        client = MagicMock()
        client.chat.completions.create.return_value = self._make_groq_response("order")
        result = _classify_intent(client, "llama-3.3-70b-versatile", "Хочу купить пергу")
        assert result == "order"

    def test_returns_track_for_shipping_question(self):
        """'track' is a valid intent; 'delivery' is not — it falls back to consult."""
        client = MagicMock()
        client.chat.completions.create.return_value = self._make_groq_response("track")
        result = _classify_intent(client, "llama-3.3-70b-versatile", "Где мой трек-номер?")
        assert result == "track"

    def test_returns_stats_for_analytics_question(self):
        client = MagicMock()
        client.chat.completions.create.return_value = self._make_groq_response("stats")
        result = _classify_intent(client, "llama-3.3-70b-versatile", "Покажи статистику продаж")
        assert result == "stats"

    def test_fallback_to_consult_on_unknown_intent(self):
        """Unknown response from LLM should fall back to consult."""
        client = MagicMock()
        client.chat.completions.create.return_value = self._make_groq_response("unknown_value")
        result = _classify_intent(client, "llama-3.3-70b-versatile", "что-то непонятное")
        assert result == "consult"

    def test_fallback_to_consult_on_api_error(self):
        """API error during classification should fall back to consult."""
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("Network error")
        result = _classify_intent(client, "llama-3.3-70b-versatile", "какой-то вопрос")
        assert result == "consult"

    def test_strips_whitespace_from_response(self):
        """LLM response may include leading/trailing whitespace."""
        client = MagicMock()
        client.chat.completions.create.return_value = self._make_groq_response("  order  ")
        result = _classify_intent(client, "llama-3.3-70b-versatile", "Хочу заказать")
        assert result == "order"


# ---------------------------------------------------------------------------
# Orchestrator.route — routing logic
# ---------------------------------------------------------------------------

class TestOrchestratorRouting:
    """Tests for Orchestrator.route() and agent dispatch."""

    def _make_orchestrator(self):
        """Create Orchestrator with mocked dependencies."""
        return _make_orchestrator_with_memory()

    @pytest.mark.asyncio
    async def test_consult_intent_routes_to_beebot(self):
        """consult intent should invoke BeebotAgent.answer."""
        orch = self._make_orchestrator()
        orch._beebot.answer = MagicMock(return_value=("Ответ о прополисе", [{"source": "pdf:X"}]))

        with patch("src.orchestrator._classify_intent", return_value="consult"):
            response, chunks = await orch.route(1001, "Как принимать прополис?")

        orch._beebot.answer.assert_called_once_with(
            "Как принимать прополис?",
            history=[],
            style=None,
            memory_facts=None,
            advice_text=None,
            user_name=None,
            system_prompt_override=None,
        )
        assert response == "Ответ о прополисе"
        assert chunks == [{"source": "pdf:X"}]

    @pytest.mark.asyncio
    async def test_order_intent_routes_to_end(self):
        """order intent should route to END (FSM handled in bot.py)."""
        orch = self._make_orchestrator()

        with patch("src.orchestrator._classify_intent", return_value="order"):
            response, chunks = await orch.route(1002, "Хочу купить пергу")

        assert chunks == []
        assert response == ""

    @pytest.mark.asyncio
    async def test_track_intent_routes_to_end(self):
        """track intent should route to END (handled in bot.py)."""
        orch = self._make_orchestrator()

        with patch("src.orchestrator._classify_intent", return_value="track"):
            response, chunks = await orch.route(1003, "Где мой заказ?")

        assert chunks == []
        assert response == ""

    @pytest.mark.asyncio
    async def test_stats_intent_routes_to_analyst(self):
        """stats intent should invoke AnalystAgent."""
        orch = self._make_orchestrator()
        orch._analyst.get_sales_summary = AsyncMock(side_effect=NotImplementedError)

        with patch("src.orchestrator._classify_intent", return_value="stats"):
            response, chunks = await orch.route(1004, "Статистика продаж")

        assert chunks == []
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_classification_error_falls_back_to_beebot(self):
        """If intent classification fails, route to BEEBOT (fallback consult)."""
        orch = self._make_orchestrator()
        orch._beebot.answer = MagicMock(return_value=("Fallback ответ", []))

        # _classify_intent raises internally but returns "consult" as fallback
        with patch("src.orchestrator._classify_intent", return_value="consult"):
            response, chunks = await orch.route(1005, "непонятный запрос")

        orch._beebot.answer.assert_called_once()
        assert response == "Fallback ответ"


# ---------------------------------------------------------------------------
# Dialog state management
# ---------------------------------------------------------------------------

class TestDialogState:
    """Tests for in-memory dialog state with TTL."""

    def _make_orchestrator(self):
        return _make_orchestrator_with_memory()

    @pytest.mark.asyncio
    async def test_stores_dialog_state_after_route(self):
        """Dialog state should be stored after routing."""
        orch = self._make_orchestrator()
        orch._beebot.answer = MagicMock(return_value=("ответ", []))

        with patch("src.orchestrator._classify_intent", return_value="consult"):
            await orch.route(2001, "вопрос")

        assert 2001 in orch._dialog_states
        assert orch._dialog_states[2001]["intent"] == "consult"

    @pytest.mark.asyncio
    async def test_get_intent_returns_stored_intent(self):
        """get_intent should return last intent for user."""
        orch = self._make_orchestrator()
        with patch("src.orchestrator._classify_intent", return_value="order"):
            await orch.route(2002, "купить пергу")

        assert orch.get_intent(2002) == "order"

    def test_get_intent_returns_none_for_unknown_user(self):
        """get_intent should return None for a user with no dialog state."""
        orch = self._make_orchestrator()
        assert orch.get_intent(9999) is None

    def test_get_intent_returns_none_for_expired_state(self):
        """Expired dialog states should not be returned."""
        orch = self._make_orchestrator()
        # Inject a stale state manually
        orch._dialog_states[3001] = {
            "user_id": 3001,
            "query": "вопрос",
            "intent": "consult",
            "response": "ответ",
            "chunks": [],
            "updated_at": time.monotonic() - (_DIALOG_TTL_SECONDS + 1),
        }
        assert orch.get_intent(3001) is None

    @pytest.mark.asyncio
    async def test_evicts_stale_states_on_route(self):
        """Stale dialog states should be evicted when a new route is processed."""
        orch = self._make_orchestrator()
        orch._beebot.answer = MagicMock(return_value=("ответ", []))

        # Inject stale state for another user
        orch._dialog_states[8888] = {
            "user_id": 8888,
            "query": "старый вопрос",
            "intent": "consult",
            "response": "старый ответ",
            "chunks": [],
            "updated_at": time.monotonic() - (_DIALOG_TTL_SECONDS + 1),
        }

        with patch("src.orchestrator._classify_intent", return_value="consult"):
            await orch.route(2003, "новый вопрос")

        assert 8888 not in orch._dialog_states
        assert 2003 in orch._dialog_states


# ---------------------------------------------------------------------------
# Zero regression: BEEBOT still works as before
# ---------------------------------------------------------------------------

class TestZeroRegression:
    """Ensure BEEBOT consult path returns same data structure as before."""

    @pytest.mark.asyncio
    async def test_beebot_response_is_string(self):
        orch = _make_orchestrator_with_memory()

        orch._beebot.answer = MagicMock(
            return_value=("Прополис принимают по 20 капель.", [{"source": "pdf:Прополис", "score": 0.9}])
        )

        with patch("src.orchestrator._classify_intent", return_value="consult"):
            response, chunks = await orch.route(4001, "как принимать прополис")

        assert isinstance(response, str)
        assert isinstance(chunks, list)
        assert len(chunks) == 1
        assert chunks[0]["source"] == "pdf:Прополис"


# ---------------------------------------------------------------------------
# M.1: LangGraph Checkpointer — история переживает рестарт
# ---------------------------------------------------------------------------

class TestCheckpointerPersistence:
    """История диалога сохраняется в SQLite и восстанавливается при создании нового Orchestrator."""

    def _make_orchestrator(self, db_path: str) -> "Orchestrator":
        """Создать Orchestrator с указанной SQLite базой для чекпоинтера."""
        with (
            patch("src.orchestrator.Groq"),
            patch("src.orchestrator.BeebotAgent"),
            patch("src.orchestrator.AnalystAgent"),
            patch("src.orchestrator.OntologyCache"),
            patch("src.orchestrator.CHECKPOINTS_DB_PATH", Path(db_path)),
        ):
            orch = Orchestrator()
        return orch

    @pytest.mark.asyncio
    async def test_history_persists_between_calls(self):
        """История диалога накапливается между вызовами route() у одного Orchestrator."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "checkpoints.db")
            orch = self._make_orchestrator(db_path)
            orch._beebot.answer = MagicMock(return_value=("Ответ 1", []))

            with patch("src.orchestrator._classify_intent", return_value="consult"):
                await orch.route(5001, "первый вопрос")

            orch._beebot.answer = MagicMock(return_value=("Ответ 2", []))
            with patch("src.orchestrator._classify_intent", return_value="consult"):
                await orch.route(5001, "второй вопрос")

            # Получить историю из чекпоинтера
            config = {"configurable": {"thread_id": "5001"}}
            saved = await orch._graph.aget_state(config)
            history = saved.values.get("history", [])

            # После двух вызовов должно быть 4 сообщения: 2 user + 2 assistant
            assert len(history) == 4
            assert history[0]["role"] == "user"
            assert history[0]["content"] == "первый вопрос"
            assert history[1]["role"] == "assistant"
            assert history[1]["content"] == "Ответ 1"
            assert history[2]["role"] == "user"
            assert history[2]["content"] == "второй вопрос"

    @pytest.mark.asyncio
    async def test_history_survives_restart(self):
        """История диалога восстанавливается после создания нового Orchestrator с тем же DB."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "checkpoints.db")

            # Первый Orchestrator — первое сообщение
            orch1 = self._make_orchestrator(db_path)
            orch1._beebot.answer = MagicMock(return_value=("Ответ о прополисе", []))

            with patch("src.orchestrator._classify_intent", return_value="consult"):
                await orch1.route(5002, "расскажи о прополисе")

            await orch1.close()

            # Второй Orchestrator (симуляция рестарта) — тот же db_path
            orch2 = self._make_orchestrator(db_path)
            orch2._beebot.answer = MagicMock(return_value=("Ответ 2", []))

            with patch("src.orchestrator._classify_intent", return_value="consult"):
                _, _ = await orch2.route(5002, "ещё вопрос")

            # История второго Orchestrator должна содержать сообщения из первого
            config = {"configurable": {"thread_id": "5002"}}
            saved = await orch2._graph.aget_state(config)
            history = saved.values.get("history", [])

            # Должно быть 4 сообщения: 2 из первой сессии + 2 из второй
            assert len(history) == 4
            assert history[0]["content"] == "расскажи о прополисе"
            assert history[1]["content"] == "Ответ о прополисе"

    @pytest.mark.asyncio
    async def test_history_limited_to_max_pairs(self):
        """История не должна расти бесконечно — максимум _MAX_HISTORY пар."""
        from src.orchestrator import _MAX_HISTORY

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "checkpoints.db")
            orch = self._make_orchestrator(db_path)

            # Делаем _MAX_HISTORY + 2 вызова
            for i in range(_MAX_HISTORY + 2):
                orch._beebot.answer = MagicMock(return_value=(f"Ответ {i}", []))
                with patch("src.orchestrator._classify_intent", return_value="consult"):
                    await orch.route(5003, f"вопрос {i}")

            config = {"configurable": {"thread_id": "5003"}}
            saved = await orch._graph.aget_state(config)
            history = saved.values.get("history", [])

            # Не больше _MAX_HISTORY пар = _MAX_HISTORY * 2 сообщений
            assert len(history) <= _MAX_HISTORY * 2
