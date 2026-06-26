"""Tests del router de intención (backend/router.py)."""
import pytest

from backend.router import Intent, IntentRouter, heuristic_classify


@pytest.mark.parametrize(
    "text, expected",
    [
        ("¿Qué fases hay en un turno de juego?", Intent.RULES),
        ("¿Cómo funciona el maná?", Intent.RULES),
        ("Busco una carta blanca de coste inferior a dos que sea guerrero", Intent.CARD_SEARCH),
        ("Quiero una carta de Han Solo, blanca-roja con dañar primero", Intent.CARD_CREATE),
        ("Crea una carta de dragón legendario", Intent.CARD_CREATE),
        ("Si mi rapaz hace daño con daña primero y la cambio con mi ninja, ¿aplico el daño?", Intent.INTERACTION),
        ("¿Qué lanzamientos o sets han salido recientemente?", Intent.RELEASES),
        ("Dime las novedades de Magic", Intent.RELEASES),
    ],
)
def test_heuristic_classify(text, expected):
    """La heurística por palabras clave clasifica cada frase en su intención."""
    assert heuristic_classify(text) == expected


def test_router_uses_llm_when_available():
    """Cuando hay LLM, el router usa su clasificación estructurada."""
    class FakeLLM:
        def extract_json(self, system, text, schema, temperature=0.0):
            return {"intent": "buscar_carta"}

    router = IntentRouter(llm=FakeLLM())
    assert router.classify("lo que sea") == Intent.CARD_SEARCH


def test_router_falls_back_to_heuristic_on_llm_error():
    """Si el LLM falla (p. ej. 429), cae a la heurística sin romperse."""
    class BrokenLLM:
        def extract_json(self, *a, **k):
            raise RuntimeError("cuota agotada (429)")

    router = IntentRouter(llm=BrokenLLM())
    # Cae a la heurística, que clasifica esto como creación de carta.
    assert router.classify("Quiero una carta nueva de goblin") == Intent.CARD_CREATE


def test_router_can_skip_llm_entirely():
    """Con use_llm=False clasifica sin tocar el LLM (testeable offline)."""
    router = IntentRouter(use_llm=False)  # nunca toca el LLM
    assert router.classify("¿Cómo funciona el maná?") == Intent.RULES
