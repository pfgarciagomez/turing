"""Tests de novedades / lanzamientos (backend/tools/releases.py).

Se mockea el cliente para probar el ordenado por fecha y el límite sin tocar la
API real.
"""
from backend.tools.releases import recent_sets


class FakeClient:
    def __init__(self, sets):
        self._sets = sets

    def get_sets(self):
        return self._sets


SETS = [
    {"code": "OLD", "name": "Set Antiguo", "releaseDate": "1994-08-05"},
    {"code": "NEW", "name": "Set Nuevo", "releaseDate": "2026-04-17"},
    {"code": "MID", "name": "Set Medio", "releaseDate": "2015-10-02"},
    {"code": "NODATE", "name": "Sin Fecha"},  # se descarta (no se puede situar)
]


def test_recent_sets_orders_by_release_date_desc():
    """Ordena los sets del más reciente al más antiguo por releaseDate."""
    out = recent_sets(FakeClient(SETS))
    assert [s["code"] for s in out] == ["NEW", "MID", "OLD"]


def test_recent_sets_drops_entries_without_date():
    """Descarta los sets sin fecha de lanzamiento."""
    out = recent_sets(FakeClient(SETS))
    assert all(s["releaseDate"] for s in out)
    assert "NODATE" not in [s["code"] for s in out]


def test_recent_sets_respects_limit():
    """Respeta el límite de resultados."""
    out = recent_sets(FakeClient(SETS), limit=2)
    assert [s["code"] for s in out] == ["NEW", "MID"]
