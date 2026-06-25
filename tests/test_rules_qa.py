"""Tests del RAG de reglas (backend/tools/rules_qa.py).

Se mockean el retriever y el LLM para probar el cableado (grounding, fuentes,
manejo de retrieval vacío) sin depender de Chroma ni de la API de Gemini.
"""
from backend.retriever import Retrieved
from backend.tools.rules_qa import RulesQA, build_context


class FakeRetriever:
    def __init__(self, hits):
        self._hits = hits

    def search(self, query, top_k=None):
        return self._hits


class CapturingLLM:
    """LLM falso que captura el system prompt y los mensajes recibidos."""

    def __init__(self, reply="Respuesta de prueba (106.1)."):
        self.reply = reply
        self.system = None
        self.messages = None

    def generate(self, system, messages, temperature=0.2):
        self.system = system
        self.messages = list(messages)
        return self.reply


HIT = Retrieved(rule_id="106.1", section="1", type="rule", text="Mana is the primary resource.", score=0.1)


def test_build_context_keeps_source_per_chunk():
    ctx = build_context([HIT])
    assert "[fuente: 106.1]" in ctx
    assert "Mana is the primary resource." in ctx


def test_answer_grounds_context_and_returns_sources():
    llm = CapturingLLM()
    qa = RulesQA(retriever=FakeRetriever([HIT]), llm=llm)
    result = qa.answer("¿Cómo funciona el maná?")

    assert result.answer == llm.reply
    assert result.sources == [HIT]
    # El contexto recuperado (con su fuente) viaja al LLM dentro de <context>.
    user_msg = llm.messages[-1]["content"]
    assert "<context>" in user_msg and "[fuente: 106.1]" in user_msg
    assert "¿Cómo funciona el maná?" in user_msg
    # El system prompt es el de grounding (exige citar y no inventar).
    assert "ÚNICAMENTE" in llm.system and "regla" in llm.system


def test_empty_retrieval_says_no_context_and_skips_llm():
    llm = CapturingLLM()
    qa = RulesQA(retriever=FakeRetriever([]), llm=llm)
    result = qa.answer("pregunta sin reglas relevantes")

    assert result.sources == []
    assert "no tengo contexto" in result.answer.lower()
    assert llm.messages is None  # no se llamó al LLM


def test_history_is_prepended_before_current_question():
    llm = CapturingLLM()
    qa = RulesQA(retriever=FakeRetriever([HIT]), llm=llm)
    history = [
        {"role": "user", "content": "anterior"},
        {"role": "model", "content": "respuesta anterior"},
    ]
    qa.answer("nueva pregunta", history=history)
    # El historial va antes, la pregunta actual (con contexto) al final.
    assert llm.messages[0]["content"] == "anterior"
    assert "nueva pregunta" in llm.messages[-1]["content"]
