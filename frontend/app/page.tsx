"use client";

import { useEffect, useRef, useState } from "react";
import { sendChat } from "@/lib/api";
import { ChatMessage, type Turn } from "@/components/ChatMessage";

// Una sugerencia por cada capacidad del enunciado, para que el evaluador
// pueda probar las 4 con un clic.
const SUGGESTIONS = [
  { cat: "Reglas", q: "¿Qué fases hay en un turno de juego?" },
  {
    cat: "Interacción",
    q: "Mi criatura tiene dañar primero y bloquea a una con toque mortal, ¿qué pasa?",
  },
  { cat: "Búsqueda", q: "Busco una carta blanca de coste inferior a dos que sea guerrero" },
  { cat: "Crear carta", q: "Quiero una carta de Han Solo, blanca-roja, que tenga dañar primero" },
];

function newSessionId(): string {
  return `web-${Math.random().toString(36).slice(2, 10)}`;
}

// Emblema de la firma: los cinco colores de maná (WUBRG).
const MANA = ["w", "u", "b", "r", "g"] as const;
function ManaPips() {
  return (
    <div className="pips" aria-hidden="true">
      {MANA.map((m) => (
        <span key={m} className={`pip pip--${m}`}>
          {m.toUpperCase()}
        </span>
      ))}
    </div>
  );
}

export default function Home() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState("default");
  const endRef = useRef<HTMLDivElement>(null);

  // session_id estable por pestaña (la memoria del backend se aísla por sesión).
  useEffect(() => setSessionId(newSessionId()), []);
  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [turns, loading]);

  async function submit(text: string) {
    const q = text.trim();
    if (!q || loading) return;
    setError(null);
    setInput("");
    setTurns((t) => [...t, { role: "user", text: q }]);
    setLoading(true);
    try {
      const data = await sendChat(q, sessionId);
      setTurns((t) => [...t, { role: "bot", data }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error desconocido");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app">
      <header className="header">
        <div className="brand">
          <div>
            <h1 className="brand__title">
              Códice <span className="accent">de Reglas</span>
            </h1>
            <p className="tagline">
              Asistente de Magic: The Gathering — cada veredicto cita su fuente.
            </p>
          </div>
          <ManaPips />
        </div>
      </header>

      <section className="chat">
        {turns.length === 0 && (
          <div className="hero">
            <div className="hero__pips">
              <ManaPips />
            </div>
            <p className="hero__title">Consulta el reglamento</p>
            <p className="hero__text">
              Reglas, interacciones entre cartas, búsqueda por descripción y diseño de cartas.
              Cada respuesta se funda en el reglamento oficial y puedes desplegar la fuente para
              ver el fragmento exacto. Empieza por una de las consultas de abajo.
            </p>
          </div>
        )}

        {turns.map((turn, i) => (
          <ChatMessage key={i} turn={turn} />
        ))}

        {loading && (
          <div className="msg msg--bot">
            <div className="bubble bubble--bot typing">Pensando…</div>
          </div>
        )}
        {error && <div className="error">⚠️ {error}</div>}
        <div ref={endRef} />
      </section>

      {/* Preguntas propuestas: siempre visibles, una por capacidad. */}
      <div className="suggestions-bar" aria-label="Preguntas propuestas">
        {SUGGESTIONS.map((s) => (
          <button
            key={s.q}
            className="suggestion-chip"
            onClick={() => submit(s.q)}
            disabled={loading}
            title={s.q}
          >
            <span className="suggestion-chip__cat">{s.cat}</span>
            <span className="suggestion-chip__q">{s.q}</span>
          </button>
        ))}
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          submit(input);
        }}
      >
        <input
          className="composer__input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escribe tu consulta sobre Magic: The Gathering…"
          disabled={loading}
        />
        <button className="composer__send" type="submit" disabled={loading || !input.trim()}>
          Enviar
        </button>
      </form>
    </main>
  );
}
