"""pytest configuration — set required environment variables before any import."""

import os
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Set dummy credentials so module-level initialisation in bot.py doesn't fail
os.environ.setdefault("GROQ_API_KEY", "test-key-placeholder")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "0000000000:AABBCCDDEEFFaabbccddeeff-placeholder")

_EMBED_DIM = 384  # paraphrase-multilingual-MiniLM-L12-v2


def _text_to_vec(text: str) -> np.ndarray:
    """Детерминированный эмбеддинг на основе символьных n-грамм.

    Похожие тексты получают близкие векторы — достаточно для тестов поиска.
    """
    vec = np.zeros(_EMBED_DIM, dtype=np.float32)
    text_lower = text.lower()
    for i in range(len(text_lower) - 1):
        bigram = text_lower[i:i + 2]
        idx = (ord(bigram[0]) * 31 + ord(bigram[1])) % _EMBED_DIM
        vec[idx] += 1.0
    norm = np.linalg.norm(vec)
    return (vec / norm) if norm > 0 else vec


def _make_fake_text_embedding():
    """Создать мок TextEmbedding с детерминированными эмбеддингами."""
    mock = MagicMock()
    mock.embed.side_effect = lambda texts: (_text_to_vec(t) for t in texts)
    return mock


@pytest.fixture(autouse=True)
def mock_fastembed(request):
    """Патчим TextEmbedding во всех тестах — ONNX-модель не нужна."""
    if request.node.get_closest_marker("real_model"):
        yield
        return

    try:
        with patch("src.knowledge_base.TextEmbedding", return_value=_make_fake_text_embedding()):
            yield
    except (ImportError, AttributeError, ModuleNotFoundError):
        # knowledge_base недоступна (нет faiss/fastembed в dev-окружении) — тест работает без патча
        yield
