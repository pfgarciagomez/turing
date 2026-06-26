"""Tests de la búsqueda de cartas (backend/tools/card_search.py).

Cubre la parte determinista (sin LLM ni API real): construcción de la query,
filtrado en cliente de rangos de cmc, caché en disco y clasificación de errores
reintentables. El HTTP se mockea con respx.
"""
import httpx
import respx

from backend.config import Settings
from backend.tools.card_search import (
    CardFilters,
    MTGCardClient,
    _apply_client_filters,
    _is_retryable,
    build_query_params,
    search_cards,
)

CARDS_URL = "https://api.magicthegathering.io/v1/cards"


def _client(tmp_path) -> MTGCardClient:
    settings = Settings(mtg_cache_dir=str(tmp_path / "cache"))
    return MTGCardClient(settings=settings, client=httpx.Client(timeout=5.0))


def test_build_query_params_maps_filters():
    """Mapea los filtros estructurados a parámetros de la API."""
    params = build_query_params(
        CardFilters(colors=["W"], subtypes=["Warrior"], cmc=1, page_size=10)
    )
    assert params["colors"] == "W"
    assert params["subtypes"] == "Warrior"
    assert params["cmc"] == "1.0" or params["cmc"] == "1"
    assert params["pageSize"] == "10"


def test_build_query_params_joins_multiple_values():
    """Une varios valores con coma (colors=W,R)."""
    params = build_query_params(CardFilters(colors=["W", "R"], types=["Creature"]))
    assert params["colors"] == "W,R"
    assert params["types"] == "Creature"


def test_cmc_max_is_filtered_client_side():
    """cmc_max se aplica en cliente, estricto (< N)."""
    cards = [{"name": "A", "cmc": 1}, {"name": "B", "cmc": 2}, {"name": "C", "cmc": 3}]
    out = _apply_client_filters(cards, CardFilters(cmc_max=2))
    assert [c["name"] for c in out] == ["A"]  # estricto: < 2


def test_cmc_min_is_filtered_client_side():
    """cmc_min se aplica en cliente (>= N)."""
    cards = [{"name": "A", "cmc": 1}, {"name": "B", "cmc": 2}, {"name": "C", "cmc": 3}]
    out = _apply_client_filters(cards, CardFilters(cmc_min=2))
    assert [c["name"] for c in out] == ["B", "C"]


@respx.mock
def test_search_uses_cache_on_second_call(tmp_path):
    """La 2ª búsqueda idéntica se sirve de la caché (no repite el HTTP)."""
    route = respx.get(CARDS_URL).mock(
        return_value=httpx.Response(200, json={"cards": [{"name": "X", "cmc": 1}]})
    )
    client = _client(tmp_path)
    filters = CardFilters(colors=["W"], subtypes=["Warrior"])

    r1 = search_cards(filters, client)
    r2 = search_cards(filters, client)

    assert route.call_count == 1  # la 2ª vez se sirve de la caché en disco
    assert r1 == r2 == [{"name": "X", "cmc": 1}]


@respx.mock
def test_search_applies_white_warrior_and_cmc_max(tmp_path):
    """Caso real del enunciado: guerrero blanco con coste < 2."""
    respx.get(CARDS_URL).mock(
        return_value=httpx.Response(
            200,
            json={"cards": [{"name": "Soldier", "cmc": 1}, {"name": "Knight", "cmc": 3}]},
        )
    )
    client = _client(tmp_path)
    # "carta blanca de coste < 2 que sea guerrero"
    filters = CardFilters(colors=["W"], subtypes=["Warrior"], cmc_max=2)
    out = search_cards(filters, client)
    assert [c["name"] for c in out] == ["Soldier"]


def test_filters_drop_sentinel_strings():
    """Neutraliza los centinelas 'null'/'none' que mete el LLM (regresión)."""
    # El LLM a veces rellena campos opcionales con "null"/"none" en vez de omitirlos;
    # el validador los neutraliza para que no contaminen la query (regresión real).
    f = CardFilters.model_validate(
        {"colors": ["W"], "cmc_max": 2, "rarity": "null", "subtypes": ["none", "Warrior"]}
    )
    assert f.rarity is None
    assert f.subtypes == ["Warrior"]
    assert "rarity" not in build_query_params(f)


def test_is_retryable_classification():
    """Solo son reintentables los errores transitorios (429/5xx/red), no los 4xx."""
    assert _is_retryable(httpx.ConnectError("boom")) is True
    resp429 = httpx.Response(429, request=httpx.Request("GET", CARDS_URL))
    resp503 = httpx.Response(503, request=httpx.Request("GET", CARDS_URL))
    resp400 = httpx.Response(400, request=httpx.Request("GET", CARDS_URL))
    assert _is_retryable(httpx.HTTPStatusError("x", request=resp429.request, response=resp429))
    assert _is_retryable(httpx.HTTPStatusError("x", request=resp503.request, response=resp503))
    # 4xx (salvo 429) no se reintenta: es un error del cliente.
    assert not _is_retryable(
        httpx.HTTPStatusError("x", request=resp400.request, response=resp400)
    )
    assert _is_retryable(ValueError("otra cosa")) is False
