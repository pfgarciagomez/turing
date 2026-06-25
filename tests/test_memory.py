"""Tests de la memoria de conversación (backend/memory.py)."""
from backend.memory import SessionMemory


def test_persists_and_reloads_across_instances(tmp_path):
    m = SessionMemory("s1", store_dir=str(tmp_path))
    m.add_turn("hola", "respuesta")
    # Una nueva instancia (p. ej. otra request) ve el historial persistido.
    again = SessionMemory("s1", store_dir=str(tmp_path))
    assert again.messages == [
        {"role": "user", "content": "hola"},
        {"role": "model", "content": "respuesta"},
    ]


def test_sessions_are_isolated(tmp_path):
    a = SessionMemory("alice", store_dir=str(tmp_path))
    b = SessionMemory("bob", store_dir=str(tmp_path))
    a.add_turn("pregunta de alice", "r")
    # La sesión de bob no ve nada de la de alice.
    assert SessionMemory("bob", store_dir=str(tmp_path)).messages == []


def test_window_is_bounded(tmp_path):
    m = SessionMemory("s", store_dir=str(tmp_path), max_turns=2)
    for i in range(5):
        m.add_turn(f"q{i}", f"a{i}")
    # Solo se conservan los 2 últimos turnos (4 mensajes).
    assert len(m.messages) == 4
    assert m.messages[0]["content"] == "q3"


def test_messages_property_returns_a_copy(tmp_path):
    m = SessionMemory("s", store_dir=str(tmp_path))
    m.add_turn("q", "a")
    snapshot = m.messages
    snapshot.append({"role": "user", "content": "mutacion externa"})
    assert len(m.messages) == 2  # el estado interno no se ve afectado


def test_session_id_is_sanitized_against_path_traversal(tmp_path):
    m = SessionMemory("../../evil", store_dir=str(tmp_path))
    m.add_turn("q", "a")
    # El fichero queda dentro de store_dir (no escapa con ../).
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1 and ".." not in files[0].name
