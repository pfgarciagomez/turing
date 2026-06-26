// Cliente del backend FastAPI. Los tipos reflejan el payload que devuelve
// Assistant.handle() (backend/assistant.py): siempre `intent` + `reply`, y según
// la capacidad, `sources` / `cards` / `card` / `filters`.

export type Intent =
  | "reglas_basicas"
  | "interaccion_cartas"
  | "buscar_carta"
  | "crear_carta";

export interface MtgCard {
  name?: string;
  manaCost?: string;
  type?: string;
  text?: string;
  cmc?: number;
  colors?: string[];
  [k: string]: unknown;
}

// Chunk recuperado del reglamento, con su texto para poder expandirlo en el front.
export interface Source {
  rule_id: string;
  section: string;
  type: string; // "rule" | "glossary"
  text: string;
  score: number; // distancia (menor = más relevante)
}

export interface CustomCard {
  name: string;
  mana_cost: string;
  colors: string[];
  type_line: string;
  rules_text: string;
  power?: string | null;
  toughness?: string | null;
  rarity?: string | null;
  flavor_text?: string | null;
}

export interface ChatResponse {
  intent: Intent;
  reply: string;
  sources?: Source[];
  cards?: MtgCard[];
  card?: CustomCard;
  filters?: Record<string, unknown>;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export async function sendChat(
  question: string,
  sessionId: string,
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`El backend respondió ${res.status}. ${detail}`.trim());
  }
  return (await res.json()) as ChatResponse;
}
