"""Configuración central del backend, leída desde entorno/.env.

Nada de secretos en el código (ver code_review.md, S1). Todos los valores tienen
defaults sensatos salvo la API key, que es obligatoria solo cuando se usa el LLM.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Gemini (chat + embeddings) ---
    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-2.5-flash"
    gemini_embed_model: str = "gemini-embedding-001"

    # --- Embeddings ---
    # "local" = sentence-transformers (coste cero, sin rate limit, cross-lingual).
    # "gemini" = API de Gemini (limitado en tier gratuito; ver decisions.md).
    embed_backend: str = "local"
    # e5 multilingüe: retrieval cross-lingual ES<->EN sólido. Usa prefijos.
    local_embed_model: str = "intfloat/multilingual-e5-base"
    local_query_prefix: str = "query: "
    local_passage_prefix: str = "passage: "

    # --- Vector store ---
    chroma_dir: str = "data/chroma"
    chroma_collection: str = "mtg_rules"

    # --- Corpus ---
    rules_txt_path: str = "data/comprehensive_rules.txt"

    # --- API de cartas ---
    mtg_api_base: str = "https://api.magicthegathering.io/v1"
    mtg_cache_dir: str = "data/cache"

    # --- RAG ---
    rag_top_k: int = 10  # nº de chunks recuperados (algunos son cortos: 1 regla = 1 chunk)
    rag_max_distance: float = 0.7  # descarta ruido: distancia > umbral (menor = más relevante)

    # --- Memoria de conversación ---
    memory_max_turns: int = 6  # turnos previos que conserva la ventana deslizante

    def require_api_key(self) -> str:
        """Devuelve la key o lanza un error claro si falta (solo al usar el LLM)."""
        if not self.gemini_api_key:
            raise RuntimeError(
                "Falta GEMINI_API_KEY. Copia .env.example a .env y rellénala "
                "(genera una gratis en https://aistudio.google.com/app/apikey)."
            )
        return self.gemini_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
