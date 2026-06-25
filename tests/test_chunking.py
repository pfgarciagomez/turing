"""Tests del chunking por número de regla (backend/ingest.py).

Se prueba contra una muestra sintética que imita el formato de las Comprehensive
Rules: secciones, grupos de reglas, reglas con subíndices (100.1, 100.1a) y un
glosario al final. No requiere ni el PDF real ni API key.
"""
from backend.ingest import RuleChunk, chunk_rules_text

# Muestra mínima con la estructura real: front matter + reglas + glosario + credits.
SAMPLE = """Magic: The Gathering Comprehensive Rules

These rules are effective as of January 1, 2026.

Contents
1. Game Concepts
5. Turn Structure

1. Game Concepts

100. General

100.1. These Magic rules apply to any Magic game with two or more players.
100.1a A two-player game is a game that begins with only two players.
100.1b A multiplayer game is a game that begins with more than two players.

100.2. To play, each player needs their own deck of traditional Magic cards.
Example: a typical deck has 60 cards.

5. Turn Structure

509. Declare Blockers Step

509.1. First, the defending player declares blockers.
509.1a The defending player chooses which creatures will block.

Glossary

First Strike
A keyword ability that lets a creature deal combat damage before creatures without first strike.

Mana
A resource used to cast spells and activate abilities.

Credits
Magic: The Gathering was designed by Richard Garfield.
"""


def _by_id(chunks: list[RuleChunk]) -> dict[str, RuleChunk]:
    return {c.rule_id: c for c in chunks}


def test_extracts_expected_rule_ids():
    chunks = chunk_rules_text(SAMPLE)
    rule_ids = {c.rule_id for c in chunks if c.type == "rule"}
    assert rule_ids == {"100.1", "100.1a", "100.1b", "100.2", "509.1", "509.1a"}


def test_section_metadata_is_first_digit():
    by_id = _by_id(chunk_rules_text(SAMPLE))
    assert by_id["100.1"].section == "1"
    assert by_id["100.1a"].section == "1"
    assert by_id["509.1a"].section == "5"


def test_rule_body_excludes_id_and_joins_continuation_lines():
    by_id = _by_id(chunk_rules_text(SAMPLE))
    # El id no debe quedar dentro del texto (viaja como metadato/fuente).
    assert by_id["100.1"].text.startswith("These Magic rules apply")
    assert "100.1" not in by_id["100.1"].text
    # La línea "Example:" se une al cuerpo de 100.2.
    assert "Example: a typical deck" in by_id["100.2"].text


def test_section_and_group_headers_do_not_create_chunks():
    chunks = chunk_rules_text(SAMPLE)
    texts = [c.text for c in chunks]
    assert "Game Concepts" not in texts
    assert "General" not in texts
    assert "Turn Structure" not in texts


def test_glossary_entries_parsed_with_type():
    by_id = _by_id(chunk_rules_text(SAMPLE))
    assert by_id["First Strike"].type == "glossary"
    assert by_id["First Strike"].section == "glossary"
    assert "combat damage before" in by_id["First Strike"].text
    assert "Mana" in by_id


def test_credits_section_stops_glossary():
    by_id = _by_id(chunk_rules_text(SAMPLE))
    # "Credits" no debe convertirse en una entrada de glosario.
    assert "Credits" not in by_id
    assert "Richard Garfield" not in " ".join(c.text for c in by_id.values())


def test_store_ids_are_unique_and_idempotent():
    chunks = chunk_rules_text(SAMPLE)
    ids = [c.store_id for c in chunks]
    assert len(ids) == len(set(ids))  # sin colisiones
    # Reparsear da exactamente los mismos ids (idempotencia de la ingesta).
    assert ids == [c.store_id for c in chunk_rules_text(SAMPLE)]


def test_empty_input_returns_no_chunks():
    assert chunk_rules_text("") == []


def test_rule_with_trailing_period_id_is_normalized():
    # "100.1." debe dar id "100.1" (sin el punto final).
    by_id = _by_id(chunk_rules_text(SAMPLE))
    assert "100.1." not in by_id
    assert "100.1" in by_id
