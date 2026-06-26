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


def _describe_filters(f: Any) -> str:
    """Resumen legible de los filtros extraídos, para mostrarlo en la traza."""
    parts: list[str] = []
    if f.colors:
        parts.append("colores=" + "/".join(f.colors))
    if f.types:
        parts.append("tipos=" + "/".join(f.types))
    if f.subtypes:
        parts.append("subtipos=" + "/".join(f.subtypes))
    if f.cmc is not None:
        parts.append(f"cmc={f.cmc:g}")
    if f.cmc_min is not None:
        parts.append(f"cmc≥{f.cmc_min:g}")
    if f.cmc_max is not None:
        parts.append(f"cmc<{f.cmc_max:g}")
    if f.power:
        parts.append(f"fuerza={f.power}")
    if f.toughness:
        parts.append(f"resistencia={f.toughness}")
    if f.rarity:
        parts.append(f"rareza={f.rarity}")
    if f.name:
        parts.append(f"nombre={f.name}")
    return ", ".join(parts) or "ninguno"


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
        import time

        trace: list[dict[str, Any]] = []

        def step(label: str, detail: str, since: float | None = None) -> None:
            entry: dict[str, Any] = {"label": label, "detail": detail}
            if since is not None:
                entry["ms"] = round((time.perf_counter() - since) * 1000)
            trace.append(entry)

        memory = SessionMemory(session_id, max_turns=self._settings.memory_max_turns)
        history = memory.messages
        prev_turns = len(history) // 2
        step(
            "Memoria de sesión",
            f"Recuperados {prev_turns} turno(s) previos del hilo"
            if prev_turns
            else "Sesión nueva, sin historial previo",
        )

        t = time.perf_counter()
        intent, method = self._get_router().classify_traced(question)
        step("Router de intención", f"Intención «{intent.value}» — clasificada vía {method}", t)

        t = time.perf_counter()
        if intent is Intent.RULES:
            res = self._get_rules_qa().answer(question, history)
            srcs = res.sources
            if srcs:
                best = max(srcs, key=lambda r: r.score)
                step(
                    "Recuperación semántica (RAG · Chroma)",
                    f"Embedding de la consulta y búsqueda top-{len(srcs)} en el reglamento · "
                    f"mejor coincidencia: regla {best.rule_id} (similitud {best.score:.3f})",
                )
            else:
                step("Recuperación semántica (RAG · Chroma)", "Sin fragmentos relevantes")
            step(
                "Generación con grounding (Gemini)",
                f"Respuesta en español fundamentada y citando {len(srcs)} fuente(s)",
                t,
            )
            payload = {"reply": res.answer, "sources": _serialize_sources(srcs)}

        elif intent is Intent.INTERACTION:
            res = self._get_interactions().resolve(question, history)
            names = ", ".join(c.get("name", "?") for c in res.cards) or "ninguna concreta"
            step(
                "Identificación de cartas (function calling → API MTG)",
                f"Cartas localizadas: {names}",
            )
            step(
                "Recuperación de reglas (RAG · Chroma)",
                f"{len(res.rules)} regla(s) relevante(s) de combate/keywords",
            )
            step(
                "Razonamiento con grounding (Gemini)",
                "Resolución de la interacción citando reglas y/o cartas",
                t,
            )
            payload = {
                "reply": res.answer,
                "sources": _serialize_sources(res.rules),
                "cards": res.cards,
            }

        elif intent is Intent.CARD_SEARCH:
            payload = self._handle_card_search(question, step, t)

        else:  # Intent.CARD_CREATE
            card = self._get_card_builder().build(question)
            step(
                "Generación estructurada (structured output)",
                f"Carta «{card.name}» generada y validada con el esquema pydantic",
                t,
            )
            payload = {
                "reply": f"He diseñado la carta «{card.name}».",
                "card": card.model_dump(),
            }

        memory.add_turn(question, payload["reply"])
        return {"intent": intent.value, "trace": trace, **payload}

    def _handle_card_search(self, question: str, step, since: float) -> dict[str, Any]:
        from backend.tools.card_search import extract_filters, search_cards

        filters = extract_filters(question, llm=self._get_llm())
        step(
            "Extracción de filtros (function calling)",
            f"Texto → filtros estructurados: {_describe_filters(filters)}",
        )
        cards = search_cards(filters, client=self._get_mtg_client())
        step(
            "Consulta a la API MTG + filtrado en cliente",
            f"{len(cards)} carta(s) cumplen los filtros (rangos de cmc aplicados en cliente)",
            since,
        )
        names = ", ".join(c.get("name", "?") for c in cards[:8])
        if cards:
            reply = f"Encontré {len(cards)} carta(s): {names}."
        else:
            reply = "No encontré cartas que cumplan esos filtros en la API."
        return {"reply": reply, "filters": filters.model_dump(), "cards": cards[:12]}
