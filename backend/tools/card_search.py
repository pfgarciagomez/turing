"""Búsqueda de cartas por descripción (capacidad 3).

Decisión clave (decisions.md): esto **no es búsqueda semántica**. "Carta blanca de
coste < 2 que sea guerrero" es una **query estructurada** (filtros). Por eso usamos
*function calling* para extraer los filtros y construimos una llamada a la API MTG,
en vez de embeddings. Es más fiable y trazable.

Capas:
  - CardFilters       : filtros estructurados (lo que el LLM extrae del texto).
  - build_query_params: filtros -> parámetros que entiende la API.
  - MTGCardClient     : HTTP con caché en disco + backoff ante 429/5xx.
  - search_cards      : orquesta query + filtrado en cliente (cmc_min/max).
  - extract_filters   : texto del usuario -> CardFilters (function calling).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from backend.config import Settings, get_settings


class CardFilters(BaseModel):
    """Filtros estructurados extraídos de la descripción del usuario."""

    name: str | None = None
    colors: list[str] = Field(default_factory=list)  # p.ej. ["W"], ["W","R"]
    types: list[str] = Field(default_factory=list)  # Creature, Instant...
    subtypes: list[str] = Field(default_factory=list)  # Warrior, Goblin...
    cmc: float | None = None  # coste convertido exacto
    cmc_min: float | None = None  # filtros de rango (cliente)
    cmc_max: float | None = None
    power: str | None = None
    toughness: str | None = None
    rarity: str | None = None
    page_size: int = 20


# Schema para la extracción por function calling (lo consume llm.extract_json).
CARD_FILTERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "colors": {"type": "array", "items": {"type": "string"}},
        "types": {"type": "array", "items": {"type": "string"}},
        "subtypes": {"type": "array", "items": {"type": "string"}},
        "cmc": {"type": "number"},
        "cmc_min": {"type": "number"},
        "cmc_max": {"type": "number"},
        "power": {"type": "string"},
        "toughness": {"type": "string"},
        "rarity": {"type": "string"},
    },
}

_FILTERS_SYSTEM = (
    "Extrae filtros de búsqueda de cartas de Magic: The Gathering a partir de la "
    "descripción del usuario (en español). Devuelve SOLO los campos mencionados. "
    "Colores en notación WUBRG: blanco=W, azul=U, negro=B, rojo=R, verde=G. "
    "Traduce el tipo/subtipo al inglés (guerrero->Warrior, criatura->Creature). "
    "Para 'coste inferior a N' usa cmc_max=N; 'superior a N' usa cmc_min=N; "
    "'coste N' usa cmc=N."
)


def build_query_params(filters: CardFilters) -> dict[str, str]:
    """Traduce los filtros a parámetros que la API MTG soporta directamente.

    Los rangos de cmc (cmc_min/cmc_max) NO los soporta la API con operadores, así que
    se aplican en cliente (ver search_cards).
    """
    params: dict[str, str] = {}
    if filters.name:
        params["name"] = filters.name
    if filters.colors:
        params["colors"] = ",".join(filters.colors)  # coma = AND en la API
    if filters.types:
        params["types"] = ",".join(filters.types)
    if filters.subtypes:
        params["subtypes"] = ",".join(filters.subtypes)
    if filters.cmc is not None:
        params["cmc"] = str(filters.cmc)
    if filters.power:
        params["power"] = filters.power
    if filters.toughness:
        params["toughness"] = filters.toughness
    if filters.rarity:
        params["rarity"] = filters.rarity
    params["pageSize"] = str(filters.page_size)
    return params


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


class MTGCardClient:
    """Cliente de api.magicthegathering.io con caché en disco y backoff."""

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self._settings = settings or get_settings()
        self._base = self._settings.mtg_api_base.rstrip("/")
        self._cache_dir = Path(self._settings.mtg_cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = client or httpx.Client(timeout=15.0)

    def _cache_path(self, params: dict[str, str]) -> Path:
        key = json.dumps(params, sort_keys=True)
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return self._cache_dir / f"cards_{digest}.json"

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(4),
        wait=wait_exponential(min=1, max=20),
    )
    def _get_cards(self, params: dict[str, str]) -> list[dict[str, Any]]:
        resp = self._client.get(f"{self._base}/cards", params=params)
        resp.raise_for_status()  # dispara backoff ante 429/5xx
        return resp.json().get("cards", [])

    def search(self, params: dict[str, str]) -> list[dict[str, Any]]:
        """Consulta con caché: no repite llamadas idénticas (ahorra cuota)."""
        cache_path = self._cache_path(params)
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))
        cards = self._get_cards(params)
        cache_path.write_text(json.dumps(cards), encoding="utf-8")
        return cards


def _apply_client_filters(cards: list[dict[str, Any]], filters: CardFilters) -> list[dict[str, Any]]:
    """Filtros que la API no soporta con operadores (rangos de cmc)."""
    out = cards
    if filters.cmc_min is not None:
        out = [c for c in out if (c.get("cmc") or 0) >= filters.cmc_min]
    if filters.cmc_max is not None:
        out = [c for c in out if (c.get("cmc") or 0) < filters.cmc_max]
    return out


def search_cards(filters: CardFilters, client: MTGCardClient | None = None) -> list[dict[str, Any]]:
    """Busca cartas a partir de filtros estructurados (con filtrado en cliente)."""
    client = client or MTGCardClient()
    params = build_query_params(filters)
    cards = client.search(params)
    return _apply_client_filters(cards, filters)


def extract_filters(user_text: str, llm: Any | None = None) -> CardFilters:
    """Extrae filtros de la descripción en lenguaje natural (function calling)."""
    if llm is None:
        from backend.llm import LLMClient

        llm = LLMClient()
    raw = llm.extract_json(_FILTERS_SYSTEM, user_text, CARD_FILTERS_SCHEMA)
    return CardFilters.model_validate(raw)
