"""Abstracción del proveedor LLM (chat + function calling) sobre Gemini.

Aísla el SDK tras una interfaz propia: cambiar de modelo/proveedor no debe tocar
la lógica de negocio (router, tools). El import del SDK es perezoso para no exigir
`google-genai` en tests que no llaman al modelo.
"""
from __future__ import annotations

from typing import Any, Sequence

from tenacity import retry, stop_after_attempt, wait_exponential

from backend.config import Settings, get_settings

Message = dict[str, str]  # {"role": "user"|"model"|"system", "content": str}


class LLMClient:
    """Interfaz mínima que necesita el resto del sistema."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._model = self._settings.gemini_chat_model
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._settings.require_api_key())
        return self._client

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(min=1, max=20))
    def generate(
        self,
        system: str,
        messages: Sequence[Message],
        temperature: float = 0.2,
    ) -> str:
        """Genera texto en español a partir de un system prompt + historial."""
        from google.genai import types

        client = self._ensure_client()
        contents = _to_gemini_contents(messages)
        resp = client.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system, temperature=temperature
            ),
        )
        return resp.text or ""

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(min=1, max=20))
    def extract_json(
        self,
        system: str,
        user_text: str,
        schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Salida estructurada (JSON) conforme a `schema`.

        Se usa para: (a) extraer filtros de búsqueda de cartas y (b) generar cartas
        custom. Es más fiable que parsear texto libre.
        """
        import json

        from google.genai import types

        client = self._ensure_client()
        resp = client.models.generate_content(
            model=self._model,
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        return json.loads(resp.text or "{}")


def _to_gemini_contents(messages: Sequence[Message]) -> list[dict[str, Any]]:
    """Convierte nuestro historial neutro al formato de Gemini (user/model)."""
    contents: list[dict[str, Any]] = []
    for m in messages:
        role = "model" if m["role"] in ("assistant", "model") else "user"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    return contents
