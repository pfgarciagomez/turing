import type { CustomCard, MtgCard } from "@/lib/api";

const COLOR_NAMES: Record<string, string> = {
  W: "Blanco",
  U: "Azul",
  B: "Negro",
  R: "Rojo",
  G: "Verde",
};

function colorClass(colors?: string[]): string {
  if (!colors || colors.length === 0) return "card--colorless";
  if (colors.length > 1) return "card--multi";
  return `card--${colors[0].toLowerCase()}`;
}

// Carta custom del bonus (capacidad 4): se renderiza como una carta de MTG.
export function CustomCardView({ card }: { card: CustomCard }) {
  return (
    <div className={`card ${colorClass(card.colors)}`}>
      <div className="card__head">
        <span className="card__name">{card.name}</span>
        <span className="card__cost">{card.mana_cost}</span>
      </div>
      <div className="card__type">{card.type_line}</div>
      {card.rules_text && <div className="card__text">{card.rules_text}</div>}
      {card.flavor_text && <div className="card__flavor">{card.flavor_text}</div>}
      <div className="card__foot">
        {card.rarity && <span className="card__rarity">{card.rarity}</span>}
        {(card.power || card.toughness) && (
          <span className="card__pt">
            {card.power ?? "?"}/{card.toughness ?? "?"}
          </span>
        )}
      </div>
    </div>
  );
}

// Carta real recuperada de la API MTG (capacidades 2 y 3).
export function ApiCardView({ card }: { card: MtgCard }) {
  return (
    <div className={`card ${colorClass(card.colors)}`}>
      <div className="card__head">
        <span className="card__name">{card.name}</span>
        {card.manaCost && <span className="card__cost">{card.manaCost}</span>}
      </div>
      {card.type && <div className="card__type">{card.type}</div>}
      {card.text && <div className="card__text">{card.text}</div>}
      <div className="card__foot">
        {card.colors && card.colors.length > 0 && (
          <span className="card__rarity">
            {card.colors.map((c) => COLOR_NAMES[c] ?? c).join(" / ")}
          </span>
        )}
        {typeof card.cmc === "number" && <span className="card__pt">CMC {card.cmc}</span>}
      </div>
    </div>
  );
}
