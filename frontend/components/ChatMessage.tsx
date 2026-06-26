import type { ChatResponse } from "@/lib/api";
import { ApiCardView, CustomCardView } from "./CardView";

export interface UserTurn {
  role: "user";
  text: string;
}
export interface BotTurn {
  role: "bot";
  data: ChatResponse;
}
export type Turn = UserTurn | BotTurn;

const INTENT_LABEL: Record<string, string> = {
  reglas_basicas: "Reglas",
  interaccion_cartas: "Interacción",
  buscar_carta: "Búsqueda",
  crear_carta: "Carta custom",
};

export function ChatMessage({ turn }: { turn: Turn }) {
  if (turn.role === "user") {
    return (
      <div className="msg msg--user">
        <div className="bubble bubble--user">{turn.text}</div>
      </div>
    );
  }

  const { data } = turn;
  return (
    <div className="msg msg--bot">
      <div className="bubble bubble--bot">
        <span className="intent-tag">{INTENT_LABEL[data.intent] ?? data.intent}</span>
        <p className="reply">{data.reply}</p>

        {data.trace && data.trace.length > 0 && (
          <details className="trace">
            <summary className="trace__summary">
              ⚙️ Cómo se generó esta respuesta ({data.trace.length} pasos)
            </summary>
            <ol className="trace__list">
              {data.trace.map((t, i) => (
                <li key={i} className="trace__step">
                  <div className="trace__head">
                    <span className="trace__label">{t.label}</span>
                    {typeof t.ms === "number" && <span className="trace__ms">{t.ms} ms</span>}
                  </div>
                  <span className="trace__detail">{t.detail}</span>
                </li>
              ))}
            </ol>
          </details>
        )}

        {data.sources && data.sources.length > 0 && (
          <div className="sources">
            <span className="sources__label">
              Fuentes ({data.sources.length}) — clic para ver el fragmento usado:
            </span>
            <div className="sources__list">
              {data.sources.map((s, i) => (
                <details key={`${s.rule_id}-${i}`} className="source">
                  <summary className="source__summary">
                    <span className="chip">{s.rule_id}</span>
                    <span className="source__meta">
                      {s.type === "glossary" ? "glosario" : `sección ${s.section}`} · sim{" "}
                      {s.score.toFixed(3)}
                    </span>
                  </summary>
                  <p className="source__text">{s.text}</p>
                </details>
              ))}
            </div>
          </div>
        )}

        {data.cards && data.cards.length > 0 && (
          <div className="card-grid">
            {data.cards.map((c, i) => (
              <ApiCardView key={`${c.name}-${i}`} card={c} />
            ))}
          </div>
        )}

        {data.card && (
          <div className="card-grid">
            <CustomCardView card={data.card} />
          </div>
        )}
      </div>
    </div>
  );
}
