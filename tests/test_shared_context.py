"""Unit tests for src/shared_context.py — SharedContextStore and UserContext."""

import time

import pytest

from src.shared_context import UserContext, SharedContextStore, _DIALOG_TTL, _MAX_HISTORY


class TestUserContext:
    """Tests for UserContext dataclass."""

    def test_is_fresh_new_context(self):
        ctx = UserContext(user_id=1)
        assert ctx.is_fresh() is True

    def test_is_not_fresh_after_ttl(self):
        ctx = UserContext(user_id=1)
        ctx.updated_at = time.monotonic() - (_DIALOG_TTL + 1)
        assert ctx.is_fresh() is False

    def test_touch_refreshes_context(self):
        ctx = UserContext(user_id=1)
        ctx.updated_at = time.monotonic() - 100
        ctx.touch()
        assert ctx.is_fresh() is True

    def test_append_history_adds_pair(self):
        ctx = UserContext(user_id=1)
        ctx.append_history("вопрос", "ответ")
        hist = ctx.get_history()
        assert len(hist) == 2
        assert hist[0] == {"role": "user", "content": "вопрос"}
        assert hist[1] == {"role": "assistant", "content": "ответ"}

    def test_append_history_trims_to_max_pairs(self):
        ctx = UserContext(user_id=1)
        for i in range(_MAX_HISTORY + 2):
            ctx.append_history(f"q{i}", f"a{i}")
        assert len(ctx.get_history()) == _MAX_HISTORY * 2

    def test_append_history_keeps_most_recent(self):
        ctx = UserContext(user_id=1)
        for i in range(_MAX_HISTORY + 1):
            ctx.append_history(f"q{i}", f"a{i}")
        hist = ctx.get_history()
        # Последний вопрос должен быть в истории
        assert any(m["content"] == f"q{_MAX_HISTORY}" for m in hist)
        # Самый первый вопрос должен быть вытеснен
        assert not any(m["content"] == "q0" for m in hist)

    def test_get_history_returns_copy(self):
        ctx = UserContext(user_id=1)
        ctx.append_history("q", "a")
        h1 = ctx.get_history()
        h1.append({"role": "user", "content": "injected"})
        assert len(ctx.get_history()) == 2  # оригинал не изменился


class TestSharedContextStore:
    """Tests for SharedContextStore."""

    def test_get_creates_new_context(self):
        store = SharedContextStore()
        ctx = store.get(42)
        assert isinstance(ctx, UserContext)
        assert ctx.user_id == 42

    def test_get_returns_same_context_twice(self):
        store = SharedContextStore()
        ctx1 = store.get(42)
        ctx2 = store.get(42)
        assert ctx1 is ctx2

    def test_get_creates_new_after_ttl(self):
        store = SharedContextStore()
        ctx1 = store.get(42)
        ctx1.append_history("q", "a")
        ctx1.updated_at = time.monotonic() - (_DIALOG_TTL + 1)

        ctx2 = store.get(42)
        assert len(ctx2.get_history()) == 0  # новый контекст, история пуста

    def test_contains_returns_true_for_fresh(self):
        store = SharedContextStore()
        store.get(99)
        assert 99 in store

    def test_contains_returns_false_for_expired(self):
        store = SharedContextStore()
        ctx = store.get(99)
        ctx.updated_at = time.monotonic() - (_DIALOG_TTL + 1)
        assert 99 not in store

    def test_evict_stale_removes_expired(self):
        store = SharedContextStore()
        ctx_fresh = store.get(1)
        ctx_stale = store.get(2)
        ctx_stale.updated_at = time.monotonic() - (_DIALOG_TTL + 1)

        removed = store.evict_stale()
        assert removed == 1
        assert 1 in store
        assert 2 not in store

    def test_len_counts_only_fresh(self):
        store = SharedContextStore()
        store.get(1)
        ctx_stale = store.get(2)
        ctx_stale.updated_at = time.monotonic() - (_DIALOG_TTL + 1)
        assert len(store) == 1
