"""Configuración de pytest para que los logs cuenten *qué* valida cada test.

En modo verboso, pytest muestra el id del test (ruta::función). Este hook le
añade la primera línea del docstring del test, de modo que al ejecutar `pytest`
se lea una descripción en español junto a cada caso, no solo su nombre. Se
conserva el id original delante, así que `-k` y la selección por ruta siguen
funcionando igual.
"""
from __future__ import annotations


def pytest_itemcollected(item) -> None:
    doc = (getattr(item.obj, "__doc__", None) or "").strip()
    if doc:
        first_line = doc.splitlines()[0].strip()
        item._nodeid = f"{item._nodeid}  |  {first_line}"
