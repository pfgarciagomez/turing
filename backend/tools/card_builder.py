"""Creación de cartas custom (bonus, capacidad 4).

Salida JSON estructurada con schema fijo (function calling / structured output). El
front la renderiza como una carta. Validamos con pydantic para garantizar la forma.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from backend.config import Settings, get_settings
from backend.prompts import CARD_BUILDER_SYSTEM


class CustomCard(BaseModel):
    """Esquema fijo de una carta custom (lo que el front sabe renderizar)."""

    name: str
    mana_cost: str = Field(description="Coste de maná en notación de símbolos, p. ej. {1}{W}{R}")
    colors: list[str] = Field(default_factory=list, description="WUBRG")
    type_line: str = Field(description="Línea de tipo, p. ej. 'Legendary Creature — Human Pilot'")
    rules_text: str = Field(default="", description="Texto de reglas/habilidades en inglés")
    power: str | None = None
    toughness: str | None = None
    rarity: str | None = None
    flavor_text: str | None = None


# JSON schema que consume llm.extract_json (structured output de Gemini).
CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "mana_cost": {"type": "string"},
        "colors": {"type": "array", "items": {"type": "string"}},
        "type_line": {"type": "string"},
        "rules_text": {"type": "string"},
        "power": {"type": "string"},
        "toughness": {"type": "string"},
        "rarity": {"type": "string"},
        "flavor_text": {"type": "string"},
    },
    "required": ["name", "mana_cost", "type_line"],
}


class CardBuilder:
    def __init__(self, llm=None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        if llm is None:
            from backend.llm import LLMClient

            llm = LLMClient(self._settings)
        self._llm = llm

    def build(self, description: str) -> CustomCard:
        raw = self._llm.extract_json(CARD_BUILDER_SYSTEM, description, CARD_SCHEMA)
        return CustomCard.model_validate(raw)
