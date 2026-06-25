"""Memoria de conversación por sesión (requisito explícito: "mantener el hilo").

Historial por sesión que se inyecta en cada turno, con:
  - aislamiento por sesión (un fichero por session_id, no uno global compartido),
  - persistencia atómica (tmp + os.replace) para no corromper en fallo a media escritura,
  - longitud acotada (ventana deslizante; en prod sería resumen — ver code_review.md C1/E1).

El formato de mensaje ({"role": "user"|"model", "content": str}) coincide con el que
espera LLMClient, así que el historial se inyecta tal cual en cada turno.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

Message = dict[str, str]


class SessionMemory:
    def __init__(
        self,
        session_id: str,
        store_dir: str = "data/sessions",
        max_turns: int = 10,
    ) -> None:
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        # Un fichero por sesión: sesiones distintas no se pisan (ver code_review C1).
        self._path = self._dir / f"{_safe_id(session_id)}.json"
        self._max_turns = max_turns
        self._messages: list[Message] = self._load()

    def _load(self) -> list[Message]:
        if not self._path.exists():
            return []
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    @property
    def messages(self) -> list[Message]:
        """Copia del historial (para inyectar en el LLM sin exponer el estado interno)."""
        return list(self._messages)

    def add_turn(self, question: str, answer: str) -> None:
        self._messages.append({"role": "user", "content": question})
        self._messages.append({"role": "model", "content": answer})
        # Ventana deslizante: acota el crecimiento (en prod: resumen de lo antiguo).
        self._messages = self._messages[-2 * self._max_turns :]
        self._persist()

    def _persist(self) -> None:
        # Escritura atómica: tmp + replace para no dejar un JSON a medias (code_review E1).
        fd, tmp = tempfile.mkstemp(dir=str(self._dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._messages, fh, ensure_ascii=False)
            os.replace(tmp, self._path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise


def _safe_id(session_id: str) -> str:
    """Evita path traversal en el nombre de fichero a partir del session_id."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)[:64] or "default"
