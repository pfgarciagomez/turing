# Documento de Decisiones Técnicas (DDT)

> Documento **vivo**. Se actualiza a medida que avanza el desarrollo, no al final.
> Objetivo: que cada decisión del sistema sea **entendible y defendible**.

## 0. Contexto y supuestos

- **Caso**: chatbot de call center para dudas de *Magic: The Gathering* (MTG).
- **Idioma de las respuestas**: **español**. El corpus (reglamento) y las cartas están en **inglés**.
  - Implicación: el retrieval es **cross-lingual** (pregunta en ES contra corpus en EN).
- **Foco de evaluación**: código limpio, testado y explicado. **No** se evalúa la veracidad del
  ruling, sí que la respuesta esté **fundamentada y sea trazable** (que cite la fuente).
- **Principio rector**: *trazabilidad > acierto*. El sistema debe citar la fuente
  (nº de regla / texto de carta) en cada respuesta. Diseñamos para *grounding*.

## 1. Stack elegido

| Capa | Elección | Por qué |
|---|---|---|
| Backend / lógica IA | **Python + FastAPI** | Ecosistema de DS/RAG vive en Python; Chroma es nativo Python; tests en `pytest`. |
| Frontend | **Next.js (App Router) + React** | UI de chat fina, deploy fácil en Vercel. Habla con el backend por HTTP. |
| LLM (chat + tools) | **Gemini Flash** (`gemini-2.5-flash`) | Tier gratuito de AI Studio; soporta *function calling* y responde bien en español. (`gemini-2.0-flash` agota la cuota gratuita enseguida → 429.) |
| Embeddings | **Locales: e5 multilingüe** (`intfloat/multilingual-e5-base`) | Coste cero, sin rate limit, offline; cross-lingual ES↔EN sólido. Ver §2.3 para por qué **no** Gemini embeddings. |
| Vector store | **Chroma** (persistente en disco) | Cero infra para la demo. En producción → gestionado (pgvector/Qdrant). |
| Datos de cartas | **API magicthegathering.io** + caché local | Cachear respuestas para no repetir llamadas ni gastar cuota (límite ~5.000 req/h). |
| Capa LLM | **Abstracción de proveedor + reintentos** | Aísla el SDK tras una interfaz propia; permite cambiar de modelo sin tocar la lógica. |

## 2. Decisiones de arquitectura

### 2.1 Backend Python + frontend Next.js (no monolito TS)
- **Decisión**: separar un backend Python (FastAPI) de un frontend Next.js, en vez de meter toda
  la lógica en API routes de Next (TypeScript).
- **Por qué**: el rol es Data Scientist / AI Engineer; el ecosistema de RAG (Chroma, parsing,
  embeddings, evaluación) es más maduro y testeable en Python. Next.js queda como capa de
  presentación fina.
- **Trade-off**: dos procesos a arrancar en local en vez de uno. Aceptable para la demo; en
  producción ya estarían desacoplados de todos modos (ver doc de arquitectura productiva).

### 2.2 Router por intención + herramientas
- Las 4 capacidades del enunciado son **problemas distintos** y cada una pide una técnica distinta:

  | Capacidad | Técnica |
  |---|---|
  | Reglas básicas | RAG sobre Comprehensive Rules |
  | Interacciones entre cartas | lookup de cartas (API) + RAG de reglas + razonamiento |
  | Búsqueda por descripción | *function calling* → query estructurada a la API |
  | Crear carta (bonus) | salida JSON estructurada con schema fijo |

- **Decisión**: un orquestador clasifica la **intención** de la consulta y enruta a la herramienta
  adecuada.
- **Clave a defender**: la búsqueda por descripción **no es búsqueda semántica**; es traducir
  lenguaje natural a una **query estructurada** (filtros color/cmc/type). *Function calling* encaja
  mejor y es más fiable que embeddings para eso.

### 2.3 Embeddings locales (e5) en vez de Gemini embeddings — **decisión revisada**
- **Plan inicial**: Gemini embeddings. **Cambio en F2**: embeddings **locales**.
- **Por qué el cambio**: el tier gratuito de Gemini embeddings limita a **100 req/min y ~1.000/día**,
  y **cada texto del lote cuenta como una request**. El reglamento son **~3.600 chunks** → embeddarlo
  entero supera la cuota diaria. Es un límite del proveedor, no del código.
- **Decisión**: `sentence-transformers` con **`intfloat/multilingual-e5-base`** (coste cero, sin rate
  limit, offline). El **chat/function-calling sí sigue en Gemini** (`gemini-2.5-flash`), que es bajo
  volumen y entra en cuota.
- **Detalle e5**: requiere prefijos `query:` / `passage:` para retrieval asimétrico; el embedder los
  aplica automáticamente. Con MiniLM (paraphrase) "¿Cómo funciona el maná?" no recuperaba la regla 106;
  con e5-base sí (dist ≈ 0.40, top-1 = 106.3). El acento de "maná" despistaba a modelos más débiles.
- **Abstracción**: `get_embedder()` permite volver a Gemini (`EMBED_BACKEND=gemini`) si hay cuota de pago.

### 2.4 Chunking por nº de regla (+ filtro de cabeceras)
- **Decisión**: `chunk_rules_text()` parte por regla numerada (`^\d{3}\.\d+[a-z]?`). Cada chunk = unidad
  citable, con metadatos `{rule_id, section, type}` y un `store_id` estable (idempotencia al reingestar).
- **Glosario**: indexado aparte como chunks `type=glossary` (mejora "¿qué es X?").
- **Filtro de ruido**: se descartan reglas-cabecera cuyo cuerpo es solo el nombre del keyword
  (p. ej. "702.118 Skulk", "205.2 Card Types"); su definición real está en la sub-regla (702.118a…).
  Estos chunks de 1-2 palabras contaminaban el retrieval de consultas cortas. Pasamos de 3.868 a 3.608.

### 2.5 Métrica coseno + parámetros de recuperación (`top_k=10`, umbral `0.25`)
- **Métrica: coseno explícito.** La colección de Chroma se crea con
  `metadata={"hnsw:space": "cosine"}`. e5 se **entrena con similitud coseno**, así que es la
  métrica natural. (Antes usábamos la L2 por defecto de Chroma sobre vectores normalizados, que
  es *equivalente en ranking* —L2² = 2·(1−cos)— pero dejarlo explícito es más limpio y no depende
  de esa equivalencia implícita.) Chroma devuelve **distancia coseno**; el retriever la convierte
  a **similitud** = `1 − distancia` (mayor = más relevante), que es más intuitivo de exponer.
- **`top_k=10` (antes 6)**: como troceamos por nº de regla, muchos chunks son muy breves (una
  sola sub-regla). Más candidatos = contexto suficiente en preguntas que dependen de varias
  sub-reglas (p. ej. combate), con coste de tokens asumible en Flash.
- **Umbral `rag_min_similarity=0.6`**: es un **mínimo de similitud** (mayor = más relevante). Las
  buenas coincidencias caen en **~0.78–0.82**; 0.6 corta el ruido sin perder lo relevante (apoyado
  además en el grounding del prompt, que ignora lo poco pertinente).
- **Garantía**: si *todo* supera el umbral, se conserva el **mejor resultado** (top-1) para no
  quedarse sin contexto en consultas límite; la capa RAG ya maneja el caso de 0 resultados.
- **Cambiar la métrica obliga a reingestar** (el espacio se fija al crear la colección).
- **Pendiente de producción**: afinar el umbral con el *golden set* (Recall@k), no a ojo.

## 3. Decisiones pendientes / por documentar
- [x] Chunking por nº de regla + glosario + filtro de cabeceras (§2.4).
- [x] Metadatos de chunk: `{rule_id, section, type}`.
- [x] Embeddings: locales e5 (§2.3); chat Gemini 2.5-flash.
- [x] Manejo de rate limit / backoff de la API MTG (`MTGCardClient`: caché en disco +
  backoff con `tenacity` solo ante 429/5xx; los 4xx de cliente no se reintentan).
- [x] Esquema JSON de la carta custom (`CustomCard` en `backend/tools/card_builder.py`:
  `name`, `mana_cost`, `colors`, `type_line`, `rules_text`, `power/toughness`, `rarity`,
  `flavor_text`; validado con pydantic).
- [x] Robustez de extracción de filtros: el LLM a veces devuelve `"null"`/`"none"` en
  campos opcionales → un validador en `CardFilters` los neutraliza (si no, `rarity="null"`
  contaminaba la query y devolvía 0 resultados).

## 4. Qué simplificamos por tiempo (y cómo iría en producción)
- Caché de la API en disco/memoria → en prod, Redis con TTL.
- Chroma local → en prod, vector DB gestionado (pgvector/Qdrant).
- Memoria de conversación en fichero por sesión → en prod, Redis/Postgres con TTL y resumen.
- Detalle completo en **[`ARCHITECTURE.md`](ARCHITECTURE.md)** (servicios, agentes,
  observabilidad, guardrails, feedback loop, CI/CD).
