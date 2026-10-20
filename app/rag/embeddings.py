from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


class EmbeddingUnavailableError(RuntimeError):
    pass


class EmbeddingModelLoadError(RuntimeError):
    pass


class EmbeddingComputationError(RuntimeError):
    pass


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


@dataclass(frozen=True)
class RetrievalSettings:
    backend: str = "lexical"
    embedding_provider: str = "none"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    min_score: float | None = None


class SentenceTransformersEmbeddingProvider:
    def __init__(self, model_name: str):
        self.model_name = model_name
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            raise EmbeddingUnavailableError("sentence-transformers is not installed") from exc
        try:
            self._model = SentenceTransformer(model_name)
        except Exception as exc:
            raise EmbeddingModelLoadError(f"failed to load embedding model: {model_name}") from exc

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        try:
            vectors = self._model.encode(texts, normalize_embeddings=True)
        except Exception as exc:
            raise EmbeddingComputationError("embedding computation failed") from exc
        return [list(map(float, vector)) for vector in vectors]


def load_retrieval_settings() -> RetrievalSettings:
    min_score_raw = os.getenv("RAG_MIN_SCORE")
    min_score = None
    if min_score_raw:
        try:
            min_score = float(min_score_raw)
        except ValueError:
            min_score = None
    return RetrievalSettings(
        backend=(os.getenv("RAG_RETRIEVAL_BACKEND") or "lexical").strip().lower(),
        embedding_provider=(os.getenv("RAG_EMBEDDING_PROVIDER") or "none").strip().lower(),
        embedding_model=(os.getenv("RAG_EMBEDDING_MODEL") or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2").strip(),
        min_score=min_score,
    )


def get_embedding_provider(settings: RetrievalSettings | None = None) -> EmbeddingProvider:
    settings = settings or load_retrieval_settings()
    if settings.embedding_provider in {"", "none"}:
        raise EmbeddingUnavailableError("RAG_EMBEDDING_PROVIDER is none")
    if settings.embedding_provider == "local":
        return SentenceTransformersEmbeddingProvider(settings.embedding_model)
    raise EmbeddingUnavailableError(f"unsupported embedding provider: {settings.embedding_provider}")
