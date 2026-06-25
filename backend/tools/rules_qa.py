"""RAG de reglas con citas (capacidad 1, y base de la 2).

Recupera las reglas relevantes y pide al LLM una respuesta en español fundamentada
SOLO en ese contexto, citando el nº de regla. Devuelve también las fuentes para
que el front pueda mostrarlas (trazabilidad > acierto; ver decisions.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from backend.config import Settings, get_settings
from backend.prompts import RULES_QA_SYSTEM
from backend.retriever import Retrieved, RulesRetriever

Message = dict[str, str]


@dataclass(frozen=True)
class RuleAnswer:
    answer: str
    sources: list[Retrieved]


def build_context(hits: Sequence[Retrieved]) -> str:
    """Construye el bloque de contexto conservando la fuente por chunk (citable)."""
    return "\n\n".join(f"[fuente: {h.rule_id}] {h.text}" for h in hits)


class RulesQA:
    def __init__(
        self,
        retriever: RulesRetriever | None = None,
        llm=None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._retriever = retriever or RulesRetriever(self._settings)
        if llm is None:
            from backend.llm import LLMClient

            llm = LLMClient(self._settings)
        self._llm = llm

    def answer(self, question: str, history: Sequence[Message] = ()) -> RuleAnswer:
        hits = self._retriever.search(question)
        if not hits:
            return RuleAnswer(
                "No tengo contexto suficiente en el reglamento para responder a eso.", []
            )
        user = f"<context>\n{build_context(hits)}\n</context>\n\nPregunta: {question}"
        messages: list[Message] = list(history) + [{"role": "user", "content": user}]
        answer = self._llm.generate(RULES_QA_SYSTEM, messages)
        return RuleAnswer(answer, hits)
