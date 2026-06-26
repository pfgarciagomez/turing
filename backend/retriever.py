"""Retriever de reglas: búsqueda semántica sobre Chroma con devolución de fuentes.

Devuelve, además del texto, el `rule_id` (la fuente citable) y la sección, de modo
que la capa de RAG pueda construir respuestas trazables (ver decisions.md:
trazabilidad > acierto). El embedder es el mismo que se usó en la ingesta para
garantizar que query y corpus viven en el mismo espacio vectorial.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.config import Settings, get_settings
from backend.embeddings import Embedder, get_embedder


@dataclass(frozen=True)
class Retrieved:
    """Un chunk recuperado, con su fuente para poder citar."""

    rule_id: str  # "509.1a" o término de glosario -> la cita
    section: str  # "1".."9" o "glossary"
    type: str  # "rule" | "glossary"
    text: str
    score: float  # distancia (menor = más relevante)


class RulesRetriever:
    def __init__(
        self,
        settings: Settings | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        import chromadb

        self._settings = settings or get_settings()
        self._embedder = embedder or get_embedder(self._settings)
        client = chromadb.PersistentClient(path=self._settings.chroma_dir)
        # get_collection (no create): si no existe, es que falta la ingesta.
        self._collection = client.get_collection(self._settings.chroma_collection)

    def search(
        self,
        query: str,
        top_k: int | None = None,
        max_distance: float | None = None,
    ) -> list[Retrieved]:
        """Top-k reglas más relevantes para la consulta (en ES o EN).

        Recupera `top_k` candidatos y descarta los que superen `max_distance`
        (ruido poco relevante). Conserva siempre al menos el mejor resultado para
        no quedarse mudo en consultas límite; quien llama decide si es suficiente.
        """
        top_k = top_k or self._settings.rag_top_k
        if max_distance is None:
            max_distance = self._settings.rag_max_distance
        q_emb = self._embedder.embed_query(query)
        res = self._collection.query(
            query_embeddings=[q_emb],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        documents = (res.get("documents") or [[]])[0]
        if not documents:
            return []
        metadatas = (res.get("metadatas") or [[]])[0]
        distances = (res.get("distances") or [[]])[0]
        # Chroma devuelve los resultados ordenados por distancia ascendente.
        hits = [
            Retrieved(
                rule_id=(meta or {}).get("rule_id", "?"),
                section=(meta or {}).get("section", "?"),
                type=(meta or {}).get("type", "rule"),
                text=doc,
                score=float(dist),
            )
            for doc, meta, dist in zip(documents, metadatas, distances)
        ]
        relevant = [h for h in hits if h.score <= max_distance]
        # Si todo supera el umbral, conserva el mejor (el primero) como mínimo.
        return relevant or hits[:1]
