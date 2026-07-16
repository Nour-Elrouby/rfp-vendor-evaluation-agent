import os
import re
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

# Sentence Transformers uses PyTorch here. Prevent an unrelated global
# TensorFlow/Keras installation from being imported by Transformers.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
)
MIN_RELEVANCE = float(os.getenv("MIN_SIMILARITY", "0.24"))
_MODEL_LOCK = Lock()
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "the", "this", "to",
    "what", "when", "where", "which", "who", "with",
}


class EmbeddingError(RuntimeError):
    """Raised when the local embedding model cannot process text."""


@lru_cache(maxsize=1)
def get_model():
    try:
        from sentence_transformers import SentenceTransformer

        try:
            return SentenceTransformer(MODEL_NAME, local_files_only=True)
        except Exception:
            return SentenceTransformer(MODEL_NAME)
    except Exception as exc:
        raise EmbeddingError(
            f"Could not load embedding model '{MODEL_NAME}'. "
            "Install dependencies and allow the first-run model download."
        ) from exc


def split_text(text: str, *, max_chars: int = 700) -> list[str]:
    """Split document text into compact, sentence-aware evidence chunks."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string.")

    units = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for unit in units:
        cleaned = re.sub(r"\s+", " ", unit).strip(" \u2022\t-")
        if not cleaned:
            continue
        if current and current_length + len(cleaned) + 1 > max_chars:
            chunks.append(" ".join(current))
            current = []
            current_length = 0
        current.append(cleaned)
        current_length += len(cleaned) + 1

    if current:
        chunks.append(" ".join(current))
    return chunks


def split_criteria(text: str) -> list[str]:
    """Split RFP criteria into independently matchable requirements."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("criteria must be a non-empty string.")

    parts = re.split(r"\n+|;|(?<=[.!?])\s+(?=[A-Z0-9])", text.strip())
    criteria = [
        re.sub(r"^\s*(?:[-\u2022*]|\d+[.)])\s*", "", part).strip()
        for part in parts
    ]
    return [criterion for criterion in criteria if criterion]


def encode(texts: list[str]) -> np.ndarray:
    if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("texts must contain non-empty strings.")
    try:
        with _MODEL_LOCK:
            vectors = get_model().encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
    except EmbeddingError:
        raise
    except Exception as exc:
        raise EmbeddingError(f"Embedding generation failed: {exc}") from exc
    return np.asarray(vectors, dtype=np.float32)


def semantic_matches(
    queries: list[str],
    passages: list[str],
    *,
    top_k: int = 1,
) -> list[list[dict[str, Any]]]:
    """Return the strongest cosine-similarity passage matches per query."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    if not queries or not passages:
        return [[] for _ in queries]

    vectors = encode(queries + passages)
    query_vectors = vectors[: len(queries)]
    passage_vectors = vectors[len(queries) :]
    similarities = query_vectors @ passage_vectors.T

    results: list[list[dict[str, Any]]] = []
    for query, row in zip(queries, similarities):
        query_terms = _content_terms(query)
        ranking_scores = np.asarray(row, dtype=np.float32).copy()
        for index, passage in enumerate(passages):
            passage_terms = _content_terms(passage)
            overlap = len(query_terms & passage_terms) / max(1, len(query_terms))
            ranking_scores[index] += 0.15 * overlap

        indices = np.argsort(ranking_scores)[::-1][: min(top_k, len(passages))]
        results.append(
            [
                {
                    "text": passages[int(index)],
                    "similarity": float(row[int(index)]),
                    "relevance": float(ranking_scores[int(index)]),
                }
                for index in indices
            ]
        )
    return results


def _content_terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in _STOP_WORDS
    }


def similarity_to_score(similarity: float) -> int:
    """Calibrate hybrid semantic relevance into a readable 0-100 evidence score."""
    # MiniLM semantic-search matches commonly occupy a narrower range than
    # 0-1. Treat 0.10 as no meaningful fit and 0.50 as a strong fit.
    calibrated = (float(similarity) - 0.10) / 0.40
    return round(max(0.0, min(1.0, calibrated)) * 100)
