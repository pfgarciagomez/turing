# MTG Assistant — Asistente conversacional de Magic: The Gathering

Chatbot de call center para resolver dudas de *Magic: The Gathering*. Responde **en
español** y **cita siempre su fuente** (nº de regla del reglamento oficial o texto de la
carta), porque en un call center importa más que la respuesta sea **trazable y defendible**
que "acertar" un ruling de memoria.

Cubre las capacidades del enunciado (4 + una ampliación de novedades):

| # | Capacidad | Técnica | Ejemplo |
|---|---|---|---|
| 1 | **Reglas básicas** | RAG sobre las *Comprehensive Rules* | *"¿Qué fases hay en un turno?"* |
| 2 | **Interacciones entre cartas** | lookup de cartas (API) + RAG de reglas + razonamiento | *"¿Cómo interactúa dañar primero con toque mortal?"* |
| 3 | **Búsqueda por descripción** | *function calling* → query estructurada a la API MTG | *"Carta blanca de coste < 2 que sea guerrero"* |
| 4 | **Crear carta** (bonus) | salida JSON estructurada (schema fijo) | *"Una carta de Han Solo, blanca-roja, con dañar primero"* |
| 5 | **Novedades / lanzamientos** | consulta en vivo a `/sets` de la API (datos factuales) | *"¿Qué sets han salido recientemente?"* |

El reto tiene dos apartados: la **implementación** (este sistema) y una **revisión de
código** (Apartado 2) en [`code_review.md`](code_review.md).

---

## Arquitectura (resumen)

```
Usuario (ES)
   │  HTTP /chat
   ▼
[ Orquestador ]
   ├─ Memoria de conversación (por sesión)
   ├─ Router de intención (LLM + fallback heurístico)
   └─ Herramienta según intención:
        reglas_basicas      → RAG sobre Comprehensive Rules  → texto + cita (nº de regla)
        interaccion_cartas  → carta(s) API + RAG reglas       → texto + reglas/cartas citadas
        buscar_carta        → function calling → query API MTG → lista de cartas
        crear_carta (bonus) → JSON estructurado               → carta maquetada
        novedades           → API MTG /sets (en vivo)         → lanzamientos recientes
   ▼
Respuesta en español + fuentes citadas
```

- **Backend**: Python + **FastAPI** (RAG, herramientas, orquestación).
- **Frontend**: **Next.js** (App Router) + React.
- **LLM**: **Gemini Flash** (`gemini-2.5-flash`) para chat y *function calling*.
- **Embeddings**: **locales** (`intfloat/multilingual-e5-base`), cross-lingual ES↔EN —
  ver [`decisions.md` §2.3](decisions.md) sobre por qué no Gemini embeddings.
- **Vector store**: **Chroma** persistente en disco.
- **Datos de cartas y sets**: API `magicthegathering.io` (`/cards` y `/sets`) en vivo, con
  caché en disco + backoff. Es la fuente **dinámica** (complementa al reglamento estático).

El detalle de cómo escalaría a producción (servicios, agentes, observabilidad, guardrails,
feedback loop, CI/CD) está en **[`ARCHITECTURE.md`](ARCHITECTURE.md)**.

---

## Puesta en marcha

Requisitos: **Python 3.11+** y **Node 18+**. Una `GEMINI_API_KEY` gratuita de
[Google AI Studio](https://aistudio.google.com/app/apikey).

### 1. Backend — entorno y configuración

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# bash / macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # y rellena GEMINI_API_KEY
```

### 2. Corpus de reglas (una vez)

El reglamento no se versiona (es regenerable y pesa ~1 MB). Descarga las *Comprehensive
Rules* oficiales en **texto** desde [magic.wizards.com/en/rules](https://magic.wizards.com/en/rules)
y guárdalo como `data/comprehensive_rules.txt` (también acepta el **PDF** del reglamento;
`RULES_TXT_PATH` lo apunta y `pdfplumber` lo extrae).

### 3. Ingesta (una vez) — chunkea e indexa en Chroma

```bash
python -m backend.ingest            # parsea, embebe e indexa (~3.600 chunks)
python -m backend.ingest --dry-run  # solo estadísticas, sin cargar (útil para verificar)
```

> La primera ejecución descarga el modelo de embeddings (~1 GB). Es idempotente:
> reingestar no duplica chunks (`store_id` estable).

### 4. Arrancar backend y frontend (dos procesos)

```bash
# Terminal 1 — API (http://localhost:8000)
uvicorn backend.api:app --reload

# Terminal 2 — frontend (http://localhost:3000)
cd frontend
npm install
npm run dev
```

Abre **http://localhost:3000**. La UI trae una sugerencia por capacidad para probar las 4
con un clic. El backend expone `GET /health` y `POST /chat`.

### Probar la API sin frontend

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "¿Qué fases hay en un turno de juego?", "session_id": "demo"}'
```

---

## Tests

```bash
pytest            # 40 tests; deterministas (no llaman al LLM ni a la API real)
```

Cubren chunking del reglamento, construcción de la query de cartas + filtrado en cliente +
caché (HTTP mockeado con `respx`), memoria de sesión, router de intención, novedades (orden
de sets) y el grounding del RAG de reglas.

---

## Estructura del repo

```
backend/
  api.py            FastAPI: /health y /chat
  assistant.py      orquestador (router → herramienta + memoria)
  router.py         clasificación de intención (LLM + fallback heurístico)
  ingest.py         parsing + chunking por nº de regla + carga en Chroma
  embeddings.py     embedder local (e5) / Gemini, conmutable
  retriever.py      búsqueda en Chroma con fuentes
  memory.py         memoria de conversación por sesión (persistencia atómica)
  llm.py            cliente Gemini (chat + structured output) con reintentos
  config.py         configuración (pydantic-settings)
  prompts/          prompts del sistema (versionados)
  tools/
    rules_qa.py     capacidad 1 (RAG + citas)
    interactions.py capacidad 2 (cartas + reglas)
    card_search.py  capacidad 3 (function calling + API MTG)
    card_builder.py capacidad 4 / bonus (JSON estructurado)
    releases.py     capacidad 5 (novedades: API /sets en vivo)
frontend/           Next.js (App Router) + React
tests/              pytest
decisions.md        Documento de Decisiones Técnicas (DDT)
code_review.md      Apartado 2 — revisión y mejora del código
ARCHITECTURE.md     arquitectura productiva
```

---

## Documentación

- **[`decisions.md`](decisions.md)** — por qué de cada decisión técnica (stack, embeddings
  locales, chunking, router…).
- **[`ARCHITECTURE.md`](ARCHITECTURE.md)** — cómo iría a producción.
- **[`code_review.md`](code_review.md)** — Apartado 2: problemas detectados en el fragmento
  dado y versión mejorada.
