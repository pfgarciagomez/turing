"""Política de reintentos compartida para las llamadas a Gemini.

Reintenta solo errores transitorios (rate limit 429, servidor 5xx, red); falla
rápido ante errores deterministas como 404 (modelo inexistente) o 400 (request
mal formada), donde reintentar no ayuda. No importa el SDK a nivel de módulo
para que los tests sin `google-genai` puedan importar el resto del backend.
"""
from __future__ import annotations

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

_RETRYABLE_CODES = {429, 500, 502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
    # Errores del SDK de Gemini exponen el código HTTP en `.code`.
    code = getattr(exc, "code", None)
    if isinstance(code, int) and code in _RETRYABLE_CODES:
        return True
    # Errores de transporte/red (timeouts, conexión caída).
    name = type(exc).__name__.lower()
    return any(k in name for k in ("timeout", "connection", "transport"))


# Decorador reutilizable: backoff exponencial, hasta 4 intentos.
gemini_retry = retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(4),
    wait=wait_exponential(min=1, max=20),
)
