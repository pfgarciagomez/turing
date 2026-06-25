"""Cliente de embeddings sobre Gemini, con batch y reintentos.

Aislado tras una interfaz propia (ver decisions.md): si mañana cambiamos de
proveedor, solo se toca este fichero. El import del SDK es perezoso para que los
tests de chunking no dependan de `google-genai`.
"""
from __future__ import annotations

from typing import Sequence

from tenacity import retry, stop_after_attempt, wait_exponential

from backend.config import Settings, get_settings


class GeminiEmbedder:
    """Genera embeddings multilingües (ES/EN en el mismo espacio vectorial)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._model = self._settings.gemini_embed_model
        self._client = None  # se crea bajo demanda (necesita la API key)

    def _ensure_client(self):
        if self._client is None:
            from google import genai  # import perezoso

            self._client = genai.Client(api_key=self._settings.require_api_key())
        return self._client

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(min=1, max=20))
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Devuelve un embedding por texto, en una sola llamada (batch)."""
        if not texts:
            return []
        client = self._ensure_client()
        resp = client.models.embed_content(model=self._model, contents=list(texts))
        return [e.values for e in resp.embeddings]
