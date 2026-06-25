"""Interacciones entre cartas (capacidad 2).

Combina tres piezas (ver decisions.md §2.2):
  1. lookup de las cartas implicadas en la API MTG (su texto real),
  2. RAG de reglas relevantes (combate/keywords) sobre el reglamento,
  3. razonamiento del LLM fundamentado SOLO en ese contexto.

No se busca acertar el ruling oficial, sino que la respuesta esté **fundamentada
y sea trazable** (cita reglas y/o cartas). Si una carta no aparece en la API
(comunitaria, puede faltar), se sigue razonando con las reglas recuperadas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from backend.config import Settings, get_settings
from backend.prompts import CARD_INTERACTION_SYSTEM
from backend.retriever import Retrieved, RulesRetriever
from backend.tools.card_search import MTGCardClient

Message = dict[str, str]

# El LLM extrae los nombres de carta (traducidos a inglés) de la pregunta en español.
_CARD_NAMES_SCHEMA = {
    "type": "object",
    "properties": {"card_names": {"type": "array", "items": {"type": "string"}}},
    "required": ["card_names"],
}
_CARD_NAMES_SYSTEM = (
    "Extrae los nombres de las cartas de Magic: The Gathering mencionadas en la "
    "consulta del usuario (en español) y tradúcelos a su nombre oficial en inglés. "
    "Devuelve solo 'card_names'. Si no hay cartas concretas, devuelve una lista vacía."
)


@dataclass(frozen=True)
class InteractionAnswer:
    answer: str
    cards: list[dict[str, Any]] = field(default_factory=list)  # cartas encontradas en la API
    rules: list[Retrieved] = field(default_factory=list)  # reglas citadas


class InteractionResolver:
    def __init__(
        self,
        retriever: RulesRetriever | None = None,
        card_client: MTGCardClient | None = None,
        llm=None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._retriever = retriever or RulesRetriever(self._settings)
        self._cards = card_client or MTGCardClient(self._settings)
        if llm is None:
            from backend.llm import LLMClient

            llm = LLMClient(self._settings)
        self._llm = llm

    def _lookup_cards(self, names: Sequence[str]) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for name in names:
            results = self._cards.search({"name": name, "pageSize": "1"})
            if results:
                c = results[0]
                found.append(
                    {
                        "name": c.get("name"),
                        "manaCost": c.get("manaCost"),
                        "type": c.get("type"),
                        "text": c.get("text", ""),
                    }
                )
        return found

    def resolve(self, question: str, history: Sequence[Message] = ()) -> InteractionAnswer:
        # 1) cartas implicadas (best-effort vía API)
        names = self._llm.extract_json(_CARD_NAMES_SYSTEM, question, _CARD_NAMES_SCHEMA).get(
            "card_names", []
        )
        cards = self._lookup_cards(names)

        # 2) reglas relevantes
        rules = self._retriever.search(question)

        # 3) contexto combinado (cartas + reglas), cada pieza con su fuente
        parts = []
        for c in cards:
            parts.append(f"[carta: {c['name']}] {c['type']} | {c.get('manaCost') or ''}\n{c['text']}")
        for r in rules:
            parts.append(f"[regla {r.rule_id}] {r.text}")
        context = "\n\n".join(parts) or "(sin contexto recuperado)"

        user = f"<context>\n{context}\n</context>\n\nPregunta: {question}"
        messages: list[Message] = list(history) + [{"role": "user", "content": user}]
        answer = self._llm.generate(CARD_INTERACTION_SYSTEM, messages)
        return InteractionAnswer(answer=answer, cards=cards, rules=rules)
