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
| LLM (chat + tools) | **Gemini Flash** (`gemini-2.0-flash`) | Tier gratuito de AI Studio (~1.500 req/día sin tarjeta); soporta *function calling* y responde bien en español. |
| Embeddings | **Gemini embeddings** (`text-embedding-004`) | Multilingües: ES y EN caen en el mismo espacio vectorial → retrieval cross-lingual sin traducir. |
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

## 3. Decisiones pendientes / por documentar
- [ ] Estrategia de chunking del reglamento (por nº de regla vs por secciones) — se fija en F2.
- [ ] Esquema de metadatos de los chunks.
- [ ] Manejo de rate limit / backoff de la API MTG.
- [ ] Esquema JSON de la carta custom (bonus).

## 4. Qué simplificamos por tiempo (y cómo iría en producción)
- Caché de la API en disco/memoria → en prod, Redis con TTL.
- Chroma local → en prod, vector DB gestionado (pgvector/Qdrant).
- Memoria de conversación en fichero por sesión → en prod, Redis/Postgres con TTL y resumen.
- (Se amplía en el documento de arquitectura productiva.)
