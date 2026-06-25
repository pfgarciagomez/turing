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

        {data.sources && data.sources.length > 0 && (
          <div className="sources">
            <span className="sources__label">Fuentes:</span>
            {data.sources.map((s, i) => (
              <span key={`${s}-${i}`} className="chip">
                {s}
              </span>
            ))}
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
