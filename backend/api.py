"""API HTTP del asistente (FastAPI).

Capa fina sobre el orquestador: el frontend Next.js habla con estos endpoints.
El Assistant se construye una vez al arrancar (carga Chroma + modelo de embeddings)
para que la primera petición no pague ese coste.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.assistant import Assistant

_state: dict[str, Assistant] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Construye el asistente al arrancar (warm-up de Chroma + embeddings).
    _state["assistant"] = Assistant()
    yield
    _state.clear()


app = FastAPI(title="MTG Assistant API", lifespan=lifespan)

# El front (Next.js, normalmente :3000) llama a esta API desde el navegador.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str = "default"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    assistant = _state["assistant"]
    return assistant.handle(req.question, session_id=req.session_id)
