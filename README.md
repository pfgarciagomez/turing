# MTG Assistant — Asistente conversacional de Magic: The Gathering

Chatbot de call center para resolver dudas de *Magic: The Gathering*: reglas básicas,
interacciones entre cartas, búsqueda de cartas por descripción y (bonus) creación de cartas
custom. Responde **en español** citando siempre la fuente (nº de regla / texto de carta).

> 🚧 **En construcción.** Este README se completa en la fase de cierre (F9). Estado actual: setup
> y revisión de código (Apartado 2) terminados.

## Arquitectura (resumen)

```
Usuario (ES)
   │
   ▼
[ Router de intención ]  ── clasifica la consulta y enruta a la herramienta adecuada
   │
   ├─ reglas_basicas      → RAG sobre Comprehensive Rules → respuesta + cita (nº de regla)
   ├─ interaccion_cartas  → lookup carta(s) en API + RAG reglas + razonamiento
   ├─ buscar_carta        → texto → query estructurada (color/cmc/type) contra API MTG
   └─ crear_carta (bonus) → salida JSON estructurada con schema fijo
   │
   ▼
[ Memoria de conversación ]  ← mantiene el hilo entre turnos
   │
   ▼
Respuesta en español + fuente citada
```

- **Backend**: Python + FastAPI (RAG, herramientas, orquestación). Vector store: Chroma.
- **Frontend**: Next.js (App Router) + React.
- **LLM**: Gemini Flash (chat + *function calling*). **Embeddings**: Gemini (multilingües).

## Documentación

- [`decisions.md`](decisions.md) — Documento de Decisiones Técnicas (DDT).
- [`code_review.md`](code_review.md) — Análisis y mejora del fragmento del Apartado 2.

## Instalación (provisional)

### Backend
```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# bash:                source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # y rellena GEMINI_API_KEY
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Configuración

Ver [`.env.example`](.env.example). Requiere una `GEMINI_API_KEY` gratuita de
[Google AI Studio](https://aistudio.google.com/app/apikey).
