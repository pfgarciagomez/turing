"""Router de intención: clasifica la consulta y la enruta a la herramienta adecuada.

Las 4 capacidades del enunciado son problemas distintos (ver decisions.md §2.2).
El router decide cuál aplicar. Estrategia: **LLM-first con fallback heurístico**:
  - Primero intenta una clasificación estructurada con el LLM (más robusta ante
    lenguaje natural variado).
  - Si el LLM falla (sin key, cuota agotada, error de red) o está deshabilitado,
    cae a una heurística determinista por palabras clave.
La heurística, además de ser red de seguridad, hace el router testeable sin red.
"""
from __future__ import annotations

import re
from enum import Enum

from backend.config import Settings, get_settings
from backend.prompts import ROUTER_SYSTEM


class Intent(str, Enum):
    RULES = "reglas_basicas"
    INTERACTION = "interaccion_cartas"
    CARD_SEARCH = "buscar_carta"
    CARD_CREATE = "crear_carta"
    RELEASES = "novedades"


_INTENT_SCHEMA = {
    "type": "object",
    "properties": {"intent": {"type": "string", "enum": [i.value for i in Intent]}},
    "required": ["intent"],
}

# Pistas léxicas para el fallback heurístico (consultas en español).
_CREATE_RE = re.compile(r"\b(crea|crear|cre[áa]me|dise[ñn]a|gen[ée]rame|invéntate|quiero una carta)\b", re.I)
_RELEASES_RE = re.compile(
    r"\b(novedad|novedades|lanzamiento|lanzamientos|nuevos? sets?|[úu]ltimos? sets?|"
    r"sets? reciente|expansi[óo]n|expansiones|releases?|qu[ée] ha salido)\b",
    re.I,
)
_SEARCH_RE = re.compile(r"\b(busco|busca|búscame|encuentra|enséñame|dame|lista|recomiéndame|cartas?)\b", re.I)
_INTERACT_RE = re.compile(r"\b(interacci[óo]n|interact[úu]a|combina|si .* (y|con) .*|aplico|bloque[ao]|ataca)\b", re.I)


def heuristic_classify(text: str) -> Intent:
    """Clasificación determinista por palabras clave (fallback / offline)."""
    t = text.lower()
    if _CREATE_RE.search(t):
        return Intent.CARD_CREATE
    if _RELEASES_RE.search(t):
        return Intent.RELEASES
    if _INTERACT_RE.search(t):
        return Intent.INTERACTION
    if _SEARCH_RE.search(t):
        return Intent.CARD_SEARCH
    return Intent.RULES


class IntentRouter:
    def __init__(self, llm=None, settings: Settings | None = None, use_llm: bool = True) -> None:
        self._settings = settings or get_settings()
        self._use_llm = use_llm
        self._llm = llm  # si None y use_llm, se crea perezosamente

    def _ensure_llm(self):
        if self._llm is None:
            from backend.llm import LLMClient

            self._llm = LLMClient(self._settings)
        return self._llm

    def classify(self, text: str) -> Intent:
        return self.classify_traced(text)[0]

    def classify_traced(self, text: str) -> tuple[Intent, str]:
        """Como `classify`, pero devuelve también el método usado ('LLM' /
        'heurística'), para poder mostrar la traza de lo que hizo el backend."""
        if self._use_llm:
            try:
                raw = self._ensure_llm().extract_json(ROUTER_SYSTEM, text, _INTENT_SCHEMA)
                return Intent(raw["intent"]), "LLM"
            except Exception:
                # Cualquier fallo (cuota, red, JSON inesperado) -> heurística.
                return heuristic_classify(text), "heurística (fallback)"
        return heuristic_classify(text), "heurística"
