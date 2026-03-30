"""Unit tests for src/gift_protocol.py — GiftBroker."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.gift_protocol import GiftBroker, Gift, _INTENT_TO_AGENT
from src.shared_context import SharedContextStore


class TestGiftBrokerSend:
    """Tests for GiftBroker.send()."""

    def _make_broker(self):
        orchestrator = MagicMock()
        orchestrator.route = AsyncMock(return_value=("ответ консультанта", [{"source": "pdf:X"}]))
        orchestrator.get_intent = MagicMock(return_value="consult")

        anamnesis = MagicMock()
        anamnesis.get = AsyncMock(return_value=[])

        ctx_store = SharedContextStore()
        crm_agent = None

        broker = GiftBroker(
            orchestrator=orchestrator,
            context_store=ctx_store,
            anamnesis=anamnesis,
            crm_agent=crm_agent,
        )
        return broker, orchestrator, anamnesis

    @pytest.mark.asyncio
    async def test_send_delegates_to_orchestrator(self):
        """GiftBroker.send() must delegate to orchestrator.route()."""
        broker, orch, _ = self._make_broker()
        response, chunks = await broker.send(1001, "Как принимать прополис?")

        orch.route.assert_called_once_with(
            1001, "Как принимать прополис?", style=None, user_name=None,
        )
        assert response == "ответ консультанта"
        assert chunks == [{"source": "pdf:X"}]

    @pytest.mark.asyncio
    async def test_send_collects_anamnesis(self):
        """GiftBroker should gather anamnesis before routing."""
        broker, _, anam = self._make_broker()
        await broker.send(2001, "вопрос")
        anam.get.assert_called_once_with(2001, None)

    @pytest.mark.asyncio
    async def test_send_passes_style_and_user_name(self):
        """GiftBroker should pass style and user_name to orchestrator."""
        broker, orch, _ = self._make_broker()
        await broker.send(3001, "вопрос", style="master", user_name="Андрей")

        orch.route.assert_called_once_with(
            3001, "вопрос", style="master", user_name="Андрей",
        )

    @pytest.mark.asyncio
    async def test_send_updates_shared_context_history(self):
        """After send(), dialog history should be updated in SharedContext."""
        broker, _, _ = self._make_broker()
        await broker.send(4001, "вопрос", user_name="Test")

        ctx = broker._ctx.get(4001)
        hist = ctx.get_history()
        assert len(hist) == 2
        assert hist[0]["content"] == "вопрос"
        assert hist[1]["content"] == "ответ консультанта"

    @pytest.mark.asyncio
    async def test_send_does_not_update_history_for_empty_response(self):
        """Empty response (order/track passthrough) should not be added to history."""
        broker, orch, _ = self._make_broker()
        orch.route = AsyncMock(return_value=("", []))
        orch.get_intent = MagicMock(return_value="order")

        await broker.send(5001, "хочу купить")

        ctx = broker._ctx.get(5001)
        assert len(ctx.get_history()) == 0

    @pytest.mark.asyncio
    async def test_get_intent_delegates_to_orchestrator(self):
        """GiftBroker.get_intent() delegates to orchestrator.get_intent()."""
        broker, orch, _ = self._make_broker()
        orch.get_intent = MagicMock(return_value="track")
        result = broker.get_intent(9001)
        assert result == "track"


class TestIntentToAgent:
    """Tests for _INTENT_TO_AGENT mapping."""

    def test_consult_maps_to_beebot(self):
        assert _INTENT_TO_AGENT["consult"] == "beebot"

    def test_order_maps_to_logist(self):
        assert _INTENT_TO_AGENT["order"] == "logist"

    def test_stats_maps_to_analyst(self):
        assert _INTENT_TO_AGENT["stats"] == "analyst"
