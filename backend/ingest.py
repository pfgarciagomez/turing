"""Ingesta del reglamento: parsing + chunking por nº de regla + carga a Chroma.

Decisión clave (decisions.md): **chunking por número de regla**, no por ventanas
ciegas. Las Comprehensive Rules están jerarquizadas (reglas tipo 100, 100.1,
100.1a; glosario al final). Cada regla numerada es semánticamente autocontenida
y **citable** → cada chunk = una unidad de fuente.

El parsing/chunking son funciones puras (sin red ni disco) para poder testarlas
aisladamente. La parte de embeddings + carga se ejecuta aparte (necesita API key).
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from itertools import batched
from pathlib import Path

from backend.config import Settings, get_settings

# Una regla numerada inicia un chunk. Acepta id con o sin punto final tras el número
# (p. ej. "100.1." y "100.1a "). El id se conserva como metadato citable.
RULE_RE = re.compile(r"^(\d{3}\.\d+[a-z]?)\.?\s+(.*)$")

# Cabeceras que NO son reglas pero delimitan: "1. Game Concepts" / "100. General".
TOP_SECTION_RE = re.compile(r"^(\d)\.\s+(\D.*)$")
RULE_GROUP_RE = re.compile(r"^(\d{3})\.\s+(\D.*)$")

# Mínimo de palabras para que un chunk de regla sea indexable. Muchas reglas
# "cabecera" (p. ej. "702.118 Skulk", "205.2 Card Types") tienen como cuerpo solo
# el nombre del keyword/título; su definición real vive en la sub-regla siguiente
# (702.118a, 205.2a...). Esos chunks de 1-2 palabras solo añaden ruido al retrieval.
MIN_RULE_WORDS = 4


@dataclass(frozen=True)
class RuleChunk:
    """Unidad citable del reglamento."""

    rule_id: str  # "509.1a" para reglas; el término para el glosario
    section: str  # "1".."9" para reglas; "glossary" para definiciones
    type: str  # "rule" | "glossary"
    text: str

    @property
    def store_id(self) -> str:
        # ID estable y único (evita colisiones regla/glosario). Idempotente al reingestar.
        return f"{self.type}:{self.rule_id}"

    def metadata(self) -> dict[str, str]:
        return {"rule_id": self.rule_id, "section": self.section, "type": self.type}


# --------------------------------------------------------------------------- #
# Parsing / chunking (puro)
# --------------------------------------------------------------------------- #
def chunk_rules_text(text: str) -> list[RuleChunk]:
    """Parte el texto del reglamento en chunks citables (reglas + glosario)."""
    lines = text.splitlines()
    chunks: list[RuleChunk] = []

    cur_id: str | None = None
    cur_lines: list[str] = []

    def flush() -> None:
        nonlocal cur_id, cur_lines
        if cur_id is not None:
            body = " ".join(s.strip() for s in cur_lines if s.strip()).strip()
            # Descarta cabeceras sin contenido real (cuerpo = nombre del keyword).
            if body and len(body.split()) >= MIN_RULE_WORDS:
                chunks.append(
                    RuleChunk(
                        rule_id=cur_id,
                        section=cur_id[0],  # primer dígito del nº de regla
                        type="rule",
                        text=body,
                    )
                )
        cur_id, cur_lines = None, []

    for i, raw in enumerate(lines):
        line = raw.rstrip()

        # Frontera con el glosario: lo procesamos aparte.
        if line.strip().lower() == "glossary" and _looks_like_glossary_start(lines, i):
            flush()
            chunks.extend(_parse_glossary(lines[i + 1 :]))
            break

        m = RULE_RE.match(line)
        if m:
            flush()
            cur_id = m.group(1)
            cur_lines = [m.group(2)]
            continue

        # Cabecera de sección / grupo: cierra la regla en curso, no crea chunk.
        if TOP_SECTION_RE.match(line) or RULE_GROUP_RE.match(line):
            flush()
            continue

        # Línea de continuación del cuerpo de la regla actual.
        if cur_id is not None and line.strip():
            cur_lines.append(line)

    flush()
    return chunks


def _looks_like_glossary_start(lines: list[str], idx: int) -> bool:
    """El glosario real va casi al final; la palabra puede aparecer antes (índice).

    Heurística: lo tratamos como inicio del glosario si está en el último tercio del
    documento. Evita confundirlo con una mención temprana.
    """
    return idx > len(lines) * 0.5


def _parse_glossary(gloss_lines: list[str]) -> list[RuleChunk]:
    """Cada entrada del glosario: término (1ª línea) + definición (resto del bloque)."""
    chunks: list[RuleChunk] = []
    block: list[str] = []

    def flush_block() -> None:
        if not block:
            return
        term = block[0].strip()
        definition = " ".join(s.strip() for s in block[1:] if s.strip()).strip()
        if term and definition:
            chunks.append(
                RuleChunk(rule_id=term, section="glossary", type="glossary", text=definition)
            )

    for raw in gloss_lines:
        line = raw.rstrip()
        if line.strip().lower() == "credits":  # fin del glosario en el doc oficial
            break
        if line.strip() == "":
            flush_block()
            block = []
        else:
            block.append(line)
    flush_block()
    return chunks


# --------------------------------------------------------------------------- #
# Lectura del corpus (TXT o PDF)
# --------------------------------------------------------------------------- #
def load_corpus_text(path: str | Path) -> str:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No se encuentra el reglamento en: {path}")
    if path.suffix.lower() == ".pdf":
        return _extract_pdf_text(path)
    # utf-8-sig: el TXT oficial de Wizards lleva BOM y comillas tipográficas.
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _extract_pdf_text(path: Path) -> str:
    import pdfplumber  # import perezoso

    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages)


# --------------------------------------------------------------------------- #
# Embeddings + carga a Chroma (necesita API key)
# --------------------------------------------------------------------------- #
def embed_and_load(
    chunks: list[RuleChunk],
    settings: Settings | None = None,
    batch_size: int = 100,
) -> int:
    import chromadb

    from backend.embeddings import get_embedder

    settings = settings or get_settings()
    embedder = get_embedder(settings)
    client = chromadb.PersistentClient(path=settings.chroma_dir)
    collection = client.get_or_create_collection(settings.chroma_collection)

    total = 0
    for batch in batched(chunks, batch_size):
        embeddings = embedder.embed([c.text for c in batch])
        collection.upsert(  # upsert = idempotente (reingestar no duplica)
            ids=[c.store_id for c in batch],
            documents=[c.text for c in batch],
            embeddings=embeddings,
            metadatas=[c.metadata() for c in batch],
        )
        total += len(batch)
    return total


def run_ingestion(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    text = load_corpus_text(settings.rules_txt_path)
    chunks = chunk_rules_text(text)
    rules = sum(1 for c in chunks if c.type == "rule")
    gloss = sum(1 for c in chunks if c.type == "glossary")
    print(f"Parseados {len(chunks)} chunks ({rules} reglas, {gloss} de glosario).")
    loaded = embed_and_load(chunks, settings)
    print(f"Cargados {loaded} chunks en Chroma ({settings.chroma_dir}).")
    return loaded


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingesta del reglamento MTG en Chroma.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo parsea y muestra estadísticas (sin embeddings ni carga).",
    )
    args = parser.parse_args()

    s = get_settings()
    if args.dry_run:
        chunks = chunk_rules_text(load_corpus_text(s.rules_txt_path))
        print(f"{len(chunks)} chunks parseados (dry-run, sin carga).")
        for c in chunks[:5]:
            print(f"  [{c.type}] {c.rule_id} -> {c.text[:70]}...")
    else:
        run_ingestion(s)
