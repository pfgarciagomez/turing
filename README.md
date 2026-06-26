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

> **Nota sobre el free tier de Gemini:** la capa gratuita limita a ~20 peticiones/día por
> modelo. Si en la demo aparece un `429 RESOURCE_EXHAUSTED`, es ese límite del proveedor, no
> un bug: el router cae a su heurística y la capacidad de **novedades funciona sin LLM**. La
> abstracción `LLMClient` permite cambiar de modelo/clave sin tocar la lógica.

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

Abre **http://localhost:3000**. La UI trae una sugerencia por capacidad para probarlas
con un clic. El backend expone `GET /health` y `POST /chat`.

---

## Ejemplos de uso

Todas las consultas van al mismo endpoint `POST /chat` con `{"question", "session_id"}`.
La respuesta es **estructurada**: siempre `intent` + `reply`, y según la capacidad añade
`sources` (reglas citadas, con su texto), `cards`, `card` o `sets`.

```bash
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"question": "¿Qué fases hay en un turno de juego?", "session_id": "demo"}'
```

| # | Pregunta de ejemplo | `intent` | La respuesta incluye |
|---|---|---|---|
| 1 | *¿Cómo funciona el maná?* | `reglas_basicas` | `reply` en español + `sources` (reglas citadas con su nº y texto) |
| 2 | *Si mi criatura con dañar primero bloquea a una con toque mortal, ¿qué pasa?* | `interaccion_cartas` | `reply` razonado + `sources` (reglas) + `cards` (cartas implicadas) |
| 3 | *Busco una carta blanca de coste inferior a dos que sea guerrero* | `buscar_carta` | `reply` + `cards` (resultados de la API) + `filters` extraídos |
| 4 | *Quiero una carta de Han Solo, blanca-roja, que tenga dañar primero* | `crear_carta` | `reply` + `card` (JSON de la carta custom) |
| 5 | *¿Qué lanzamientos o sets han salido recientemente?* | `novedades` | `reply` + `sets` (lanzamientos recientes por fecha) |

Cada respuesta del front muestra además un panel **"cómo se generó"** (la traza: router →
herramientas → LLM) y las **fuentes desplegables** con el fragmento exacto del reglamento.

### Respuestas completas por capacidad

> Respuestas representativas (texto del LLM y `ms` varían entre ejecuciones; el reglamento y
> las cartas están en inglés, las respuestas en español). El campo `trace` se omite aquí por
> brevedad salvo en el primer ejemplo.

<details>
<summary><b>1. Reglas básicas</b> — <i>¿Cómo funciona el maná?</i></summary>

```json
{
  "intent": "reglas_basicas",
  "reply": "El maná es el recurso principal del juego (106.1). Los jugadores gastan maná para pagar costes, generalmente al lanzar hechizos y activar habilidades (106.1). El maná es producido por los efectos de habilidades de maná (106.3). Las habilidades de maná se resuelven inmediatamente (405.6c).",
  "trace": [
    {"label": "Memoria de sesión", "detail": "Sesión nueva, sin historial previo"},
    {"label": "Router de intención", "detail": "Intención «reglas_basicas» — clasificada vía LLM", "ms": 1957},
    {"label": "Recuperación semántica (RAG · Chroma)", "detail": "top-6 en el reglamento · mejor coincidencia: regla 405.6c (similitud 0.798)"},
    {"label": "Generación con grounding (Gemini)", "detail": "Respuesta en español citando 6 fuente(s)", "ms": 11168}
  ],
  "sources": [
    {"rule_id": "405.6c", "section": "4", "type": "rule", "score": 0.798, "text": "Mana abilities resolve immediately. If a mana ability both produces mana and has another effect, the mana is produced and the other effect happens immediately."},
    {"rule_id": "106.3", "section": "1", "type": "rule", "score": 0.796, "text": "Mana is produced by the effects of mana abilities (see rule 605). It may also be produced by other spells or abilities."},
    {"rule_id": "106.1", "section": "1", "type": "rule", "score": 0.789, "text": "Mana is the primary resource in the game. Players spend mana to pay costs, usually when casting spells and activating abilities."}
  ]
}
```
</details>

<details>
<summary><b>2. Interacciones entre cartas</b> — <i>Si mi criatura con dañar primero bloquea a una con toque mortal, ¿qué pasa?</i></summary>

```json
{
  "intent": "interaccion_cartas",
  "reply": "Como al menos una de las criaturas tiene dañar primero, hay dos pasos de daño de combate (510.5). En el primer paso, tu criatura con dañar primero asigna su daño a la criatura con toque mortal. Si ese daño es de 1 o más, es letal por el toque mortal solo si la fuente tuviera toque mortal; tu criatura no lo tiene, así que destruye a la otra solo si iguala su resistencia (510.1c, 702.7b). Si la criatura con toque mortal muere en el primer paso, no llega al segundo y no te devuelve daño (702.2c).",
  "sources": [
    {"rule_id": "702.7b", "section": "7", "type": "rule", "score": 0.74, "text": "A creature with first strike deals its combat damage before creatures without first strike."},
    {"rule_id": "702.2c", "section": "7", "type": "rule", "score": 0.73, "text": "Any nonzero amount of combat damage assigned to a creature by a source with deathtouch is considered to be lethal damage."},
    {"rule_id": "510.5", "section": "5", "type": "rule", "score": 0.72, "text": "If at least one attacking or blocking creature has first strike or double strike, the combat damage step is divided into two."}
  ],
  "cards": []
}
```

> `cards` viene vacío cuando la consulta no nombra cartas concretas; si nombra cartas que están
> en la API, aparecen aquí con su `name`, `manaCost`, `type` y `text`.
</details>

<details>
<summary><b>3. Búsqueda por descripción</b> — <i>Busco una carta blanca de coste inferior a dos que sea guerrero</i></summary>

```json
{
  "intent": "buscar_carta",
  "reply": "Encontré 1 carta(s): Rhys the Redeemed.",
  "filters": {"colors": ["W"], "subtypes": ["Warrior"], "cmc_max": 2.0, "page_size": 20},
  "cards": [
    {
      "name": "Rhys the Redeemed",
      "manaCost": "{G/W}",
      "cmc": 1,
      "colors": ["White", "Green"],
      "type": "Legendary Creature — Elf Warrior",
      "rarity": "Mythic Rare",
      "text": "{4}{G/W}{G/W}, {T}: Create a 1/1 green and white Elf Warrior creature token..."
    }
  ]
}
```

> La búsqueda **no es semántica**: el LLM traduce el texto a `filters` estructurados
> (function calling) y se consulta la API; los rangos de coste se filtran en cliente.
</details>

<details>
<summary><b>4. Crear carta (bonus)</b> — <i>Quiero una carta de Han Solo, blanca-roja, que tenga dañar primero</i></summary>

```json
{
  "intent": "crear_carta",
  "reply": "He diseñado la carta «Han Solo, Smuggler Captain».",
  "card": {
    "name": "Han Solo, Smuggler Captain",
    "mana_cost": "1RW",
    "colors": ["Red", "White"],
    "type_line": "Legendary Creature - Human Rogue",
    "rules_text": "First strike. Whenever Han Solo, Smuggler Captain attacks, flip a coin. If you win the flip, Han Solo gains double strike until end of turn.",
    "power": "3",
    "toughness": "2",
    "rarity": "Rare",
    "flavor_text": "\"Never tell me the odds.\""
  }
}
```
</details>

<details>
<summary><b>5. Novedades / lanzamientos</b> — <i>¿Qué lanzamientos o sets han salido recientemente?</i></summary>

```json
{
  "intent": "novedades",
  "reply": "Los lanzamientos más recientes de Magic son: Bloomburrow (2024-08-02); Cowboy Bebop (2024-08-02); Assassin's Creed (2024-07-05); Modern Horizons 3 Commander (2024-06-07); Modern Horizons 3 (2024-06-07).",
  "sets": [
    {"code": "BLB", "name": "Bloomburrow", "type": "expansion", "releaseDate": "2024-08-02", "block": null},
    {"code": "ACR", "name": "Assassin's Creed", "type": "draft_innovation", "releaseDate": "2024-07-05", "block": null},
    {"code": "MH3", "name": "Modern Horizons 3", "type": "draft_innovation", "releaseDate": "2024-06-07", "block": null}
  ]
}
```

> Capacidad **sin LLM** (datos factuales): consulta `/sets` en vivo y ordena por fecha. La API
> es comunitaria y puede ir por detrás de los lanzamientos más recientes.
</details>

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
