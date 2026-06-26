"""Novedades / nuevos lanzamientos (capacidad 5).

Segunda fuente viva del sistema (además del reglamento estático): la API MTG.
Las cartas y los sets cambian con cada release, así que NO se indexan en el RAG;
se consultan en tiempo real. Aquí se listan los sets más recientes por fecha.
"""
from __future__ import annotations

from typing import Any

from backend.tools.card_search import MTGCardClient


def recent_sets(client: MTGCardClient | None = None, limit: int = 8) -> list[dict[str, Any]]:
    """Devuelve los `limit` sets más recientes ordenados por fecha de lanzamiento.

    El `releaseDate` viene como ISO 'YYYY-MM-DD' (ordena lexicográficamente bien).
    Se descartan los sets sin fecha (no se pueden situar en el tiempo).
    """
    client = client or MTGCardClient()
    sets = client.get_sets()
    with_date = [s for s in sets if s.get("releaseDate")]
    with_date.sort(key=lambda s: s["releaseDate"], reverse=True)
    return [
        {
            "code": s.get("code"),
            "name": s.get("name"),
            "type": s.get("type"),
            "releaseDate": s.get("releaseDate"),
            "block": s.get("block"),
        }
        for s in with_date[:limit]
    ]
