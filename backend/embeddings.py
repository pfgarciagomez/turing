"""Embeddings multilingües (ES/EN en el mismo espacio vectorial) tras una interfaz propia.

Dos backends intercambiables (ver decisions.md):
  - LocalEmbedder (default): sentence-transformers con un modelo e5 multilingüe.
    Coste cero, sin rate limit, offline. Es el usado para ingerir las ~3.600
    reglas del reglamento.
  - GeminiEmbedder: API de Gemini. Mejor calidad pero el tier gratuito limita a
    100 req/min y ~1.000/día, inviable para todo el corpus.

Los modelos e5 distinguen entre consultas y documentos mediante los prefijos
`query:` / `passage:`, así que la interfaz separa `embed_query` (1 consulta) de
`embed` (lote de documentos/pasajes). `get_embedder()` elige según EMBED_BACKEND.
Los imports de SDK/modelo son perezosos para que los tests de chunking no dependan
de ellos.
"""
from __future__ import annotations

from typing import Protocol, Sequence

from backend.config import Settings, get_settings
from backend.gemini_retry import gemini_retry


class Embedder(Protocol):
    """Interfaz mínima que necesita el resto del sistema."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embeddings de documentos/pasajes (para indexar)."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embedding de una consulta (para buscar)."""
        ...


class LocalEmbedder:
    """Embeddings locales con sentence-transformers (modelo e5 multilingüe)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._model_name = self._settings.local_embed_model
        self._query_prefix = self._settings.local_query_prefix
        self._passage_prefix = self._settings.local_passage_prefix
        self._model = None  # carga perezosa (descarga el modelo la 1ª vez)

    def _ensure_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        model = self._ensure_model()
        vecs = model.encode(list(texts), normalize_embeddings=True)
        return [v.tolist() for v in vecs]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._encode([self._passage_prefix + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([self._query_prefix + text])[0]


class GeminiEmbedder:
    """Embeddings vía API de Gemini, en batch y con reintentos."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._model = self._settings.gemini_embed_model
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from google import genai  # import perezoso

            self._client = genai.Client(api_key=self._settings.require_api_key())
        return self._client

    @gemini_retry
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._ensure_client()
        resp = client.models.embed_content(model=self._model, contents=list(texts))
        return [e.values for e in resp.embeddings]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


def get_embedder(settings: Settings | None = None) -> Embedder:
    """Devuelve el embedder configurado por EMBED_BACKEND (default: local)."""
    settings = settings or get_settings()
    if settings.embed_backend == "gemini":
        return GeminiEmbedder(settings)
    return LocalEmbedder(settings)
