"""Orquestador del asistente: router de intención -> herramienta + memoria.

Es el patrón "agente + servicios" del enunciado: un único punto de entrada
(`handle`) que clasifica la intención, ejecuta la herramienta adecuada y mantiene
el hilo de la conversación por sesión. Devuelve una respuesta estructurada que el
front sabe renderizar (texto + fuentes/cartas/carta custom).

Los componentes pesados (retriever con Chroma + modelo de embeddings) se construyen
una sola vez y se reutilizan entre llamadas.
"""
from __future__ import annotations

from typing import Any, Sequence

from backend.config import Settings, get_settings
from backend.memory import SessionMemory
from backend.router import Intent, IntentRouter


def _serialize_sources(rules: Sequence[Any]) -> list[dict[str, Any]]:
    """Serializa los chunks recuperados con su texto, para que el front pueda
    mostrar la fuente expandible (no solo el nº de regla)."""
    return [
        {
            "rule_id": r.rule_id,
            "section": r.section,
            "type": r.type,
            "text": r.text,
            "score": round(float(r.score), 4),
        }
        for r in rules
    ]


class Assistant:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        # Construcción perezosa: el primer uso de cada capacidad la inicializa.
        self._router: IntentRouter | None = None
        self._rules_qa = None
        self._interactions = None
        self._card_builder = None
        self._mtg_client = None
        self._llm = None

    # --- accesores perezosos -------------------------------------------------
    def _get_llm(self):
        if self._llm is None:
            from backend.llm import LLMClient

            self._llm = LLMClient(self._settings)
        return self._llm

    def _get_router(self) -> IntentRouter:
        if self._router is None:
            self._router = IntentRouter(llm=self._get_llm(), settings=self._settings)
        return self._router

    def _get_rules_qa(self):
        if self._rules_qa is None:
            from backend.tools.rules_qa import RulesQA

            self._rules_qa = RulesQA(llm=self._get_llm(), settings=self._settings)
        return self._rules_qa

    def _get_interactions(self):
        if self._interactions is None:
            from backend.tools.interactions import InteractionResolver

            self._interactions = InteractionResolver(
                card_client=self._get_mtg_client(), llm=self._get_llm(), settings=self._settings
            )
        return self._interactions

    def _get_card_builder(self):
        if self._card_builder is None:
            from backend.tools.card_builder import CardBuilder

            self._card_builder = CardBuilder(llm=self._get_llm(), settings=self._settings)
        return self._card_builder

    def _get_mtg_client(self):
        if self._mtg_client is None:
            from backend.tools.card_search import MTGCardClient

            self._mtg_client = MTGCardClient(self._settings)
        return self._mtg_client

    # --- punto de entrada ----------------------------------------------------
    def handle(self, question: str, session_id: str = "default") -> dict[str, Any]:
        memory = SessionMemory(session_id, max_turns=self._settings.rag_top_k)
        history = memory.messages
        intent = self._get_router().classify(question)

        if intent is Intent.RULES:
            res = self._get_rules_qa().answer(question, history)
            payload = {"reply": res.answer, "sources": _serialize_sources(res.sources)}

        elif intent is Intent.INTERACTION:
            res = self._get_interactions().resolve(question, history)
            payload = {
                "reply": res.answer,
                "sources": _serialize_sources(res.rules),
                "cards": res.cards,
            }

        elif intent is Intent.CARD_SEARCH:
            payload = self._handle_card_search(question)

        else:  # Intent.CARD_CREATE
            card = self._get_card_builder().build(question)
            payload = {
                "reply": f"He diseñado la carta «{card.name}».",
                "card": card.model_dump(),
            }

        memory.add_turn(question, payload["reply"])
        return {"intent": intent.value, **payload}

    def _handle_card_search(self, question: str) -> dict[str, Any]:
        from backend.tools.card_search import extract_filters, search_cards

        filters = extract_filters(question, llm=self._get_llm())
        cards = search_cards(filters, client=self._get_mtg_client())
        names = ", ".join(c.get("name", "?") for c in cards[:8])
        if cards:
            reply = f"Encontré {len(cards)} carta(s): {names}."
        else:
            reply = "No encontré cartas que cumplan esos filtros en la API."
        return {"reply": reply, "filters": filters.model_dump(), "cards": cards[:12]}
