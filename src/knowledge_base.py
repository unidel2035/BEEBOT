"""Hybrid knowledge base: semantic search (FAISS) + stylometric features."""

import json
import re
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import (
    EMBEDDING_MODEL,
    FAISS_INDEX_PATH,
    CHUNKS_PATH,
    PROCESSED_DIR,
    MAX_CONTEXT_CHUNKS,
)


class StyleAnalyzer:
    """Lightweight stylometric feature extractor."""

    def extract_features(self, text: str) -> dict:
        sentences = re.split(r"[.!?]+", text)
        sentences = [s.strip() for s in sentences if s.strip()]
        words = text.split()

        avg_sentence_len = np.mean([len(s.split()) for s in sentences]) if sentences else 0
        avg_word_len = np.mean([len(w) for w in words]) if words else 0
        exclamation_ratio = text.count("!") / max(len(sentences), 1)
        question_ratio = text.count("?") / max(len(sentences), 1)
        comma_ratio = text.count(",") / max(len(words), 1)

        return {
            "avg_sentence_len": float(avg_sentence_len),
            "avg_word_len": float(avg_word_len),
            "exclamation_ratio": float(exclamation_ratio),
            "question_ratio": float(question_ratio),
            "comma_ratio": float(comma_ratio),
        }

    def to_vector(self, text: str) -> np.ndarray:
        feats = self.extract_features(text)
        return np.array(list(feats.values()), dtype=np.float32)


class KnowledgeBase:
    """Hybrid vector knowledge base with semantic + stylometric search."""

    def __init__(self):
        self.model: SentenceTransformer | None = None
        self.style_analyzer = StyleAnalyzer()
        self.index: faiss.IndexFlatIP | None = None
        self.chunks: list[dict] = []
        self.semantic_dim = 0
        self.style_dim = 5  # number of stylometric features

    def _load_model(self):
        if self.model is None:
            self.model = SentenceTransformer(EMBEDDING_MODEL)
            self.semantic_dim = self.model.get_sentence_embedding_dimension()

    def build(self, documents: list[dict], chunk_size: int = 600, chunk_overlap: int = 100):
        """Build the index from a list of documents."""
        self._load_model()

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " "],
        )

        self.chunks = []
        for doc in documents:
            text_chunks = splitter.split_text(doc["text"])
            for i, chunk_text in enumerate(text_chunks):
                self.chunks.append({
                    "text": chunk_text,
                    "source": doc["source"],
                    "chunk_index": i,
                })

        if not self.chunks:
            raise ValueError("No chunks to index")

        texts = [c["text"] for c in self.chunks]

        # Semantic embeddings
        sem_embeddings = self.model.encode(texts, show_progress_bar=True, normalize_embeddings=True)

        # Stylometric features (normalized)
        style_vectors = np.array([self.style_analyzer.to_vector(t) for t in texts])
        if style_vectors.shape[0] > 0:
            norms = np.linalg.norm(style_vectors, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)
            style_vectors = style_vectors / norms

        # Combine: 70% semantic + 30% style
        combined = np.hstack([
            sem_embeddings * 0.7,
            style_vectors * 0.3,
        ]).astype(np.float32)

        # Build FAISS index (inner product on normalized vectors)
        dim = combined.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        faiss.normalize_L2(combined)
        self.index.add(combined)

        self._save()
        return len(self.chunks)

    def _save(self):
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(FAISS_INDEX_PATH))
        with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
            json.dump(self.chunks, f, ensure_ascii=False, indent=2)

    def load(self):
        """Load existing index and chunks from disk."""
        self._load_model()
        self.index = faiss.read_index(str(FAISS_INDEX_PATH))
        with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
            self.chunks = json.load(f)

    # Keyword → source name mapping for direct product queries
    KEYWORD_SOURCES = {
        "перга":         "pdf:Перга",
        "пергу":         "pdf:Перга",
        "пергой":        "pdf:Перга",
        "гомогенат":     "pdf:Трутнёвый гомогенат",
        "гомогената":    "pdf:Трутнёвый гомогенат",
        "трутнёвый":     "pdf:Трутнёвый гомогенат",
        "трутневый":     "pdf:Трутнёвый гомогенат",
        "гемогенат":     "pdf:Трутнёвый гомогенат",
        "успокоин":      "pdf:Настойка «Успокоин» (Травяная)",
        "пжвм":          "pdf:Настойка ПЖВМ",
        "огнёвка":       "pdf:Настойка ПЖВМ",
        "огневка":       "pdf:Настойка ПЖВМ",
        "подмор":        "pdf:Настойка Подмора пчелиного (на самогоне 40°)",
        "подмора":       "pdf:Настойка Подмора пчелиного (на самогоне 40°)",
        "прополис":      "pdf:Прополис_ сухой + настойка",
        "прополиса":     "pdf:Прополис_ сухой + настойка",
        "обножка":       "pdf:Пчелиная обножка",
        "обножки":       "pdf:Пчелиная обножка",
        "пыльца":        "pdf:Пчелиная обножка",
        "антивирус":     "pdf:Антивирус",
        "фитоэнергия":   "pdf:ФитоЭнергия",
        "иммунитет":     "pdf:Иммунитет ребенка",
    }

    def _keyword_chunks(self, query: str, n: int = 2) -> list[dict]:
        """Return top-n chunks from a product source if query contains a keyword."""
        query_lower = query.lower()
        for keyword, source in self.KEYWORD_SOURCES.items():
            if keyword in query_lower:
                matched = [c for c in self.chunks if c.get("source") == source]
                # Return first n chunks from that source with boosted score
                return [dict(c, score=1.0) for c in matched[:n]]
        return []

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        """Search for the most relevant chunks given a query."""
        if self.index is None:
            self.load()

        top_k = top_k or MAX_CONTEXT_CHUNKS

        # Keyword boost: if query names a product directly, pin its chunks first
        keyword_results = self._keyword_chunks(query, n=2)
        keyword_sources = {id(c) for c in keyword_results}

        # Encode query the same way
        sem_query = self.model.encode([query], normalize_embeddings=True)
        style_query = self.style_analyzer.to_vector(query).reshape(1, -1)
        norm = np.linalg.norm(style_query)
        if norm > 0:
            style_query = style_query / norm

        combined_query = np.hstack([
            sem_query * 0.7,
            style_query * 0.3,
        ]).astype(np.float32)
        faiss.normalize_L2(combined_query)

        scores, indices = self.index.search(combined_query, top_k * 2)

        seen_texts = {c["text"] for c in keyword_results}
        semantic_results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0:
                chunk = self.chunks[idx].copy()
                if chunk["text"] not in seen_texts:
                    chunk["score"] = float(score)
                    semantic_results.append(chunk)
                    seen_texts.add(chunk["text"])

        # Keyword chunks first, then fill with semantic results
        combined = keyword_results + semantic_results
        return combined[:top_k]


if __name__ == "__main__":
    from src.pdf_loader import process_all_pdfs

    documents = process_all_pdfs()
    kb = KnowledgeBase()
    n = kb.build(documents)
    print(f"Built index with {n} chunks")

    results = kb.search("Как принимать настойку прополиса?")
    for r in results:
        print(f"\n[{r['score']:.3f}] ({r['source']})")
        print(f"  {r['text'][:150]}...")
