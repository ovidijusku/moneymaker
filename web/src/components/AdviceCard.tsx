import type { Advice, Signal } from "../api";

const LABELS: Record<string, string> = {
  trend_ema: "Trend",
  momentum_rsi: "Momentum",
  sentiment_news: "News",
  sentiment_social: "Social",
};

function SignalBar({ signal }: { signal: Signal }) {
  const magnitude = Math.abs(signal.value) * 50;
  const muted = signal.weight === 0;
  return (
    <div className={`signal ${muted ? "signal--muted" : ""}`} title={signal.evidence.join("\n")}>
      <span className="signal__name">{LABELS[signal.name] ?? signal.name}</span>
      <div className="signal__track">
        <span
          className={`signal__fill signal__fill--${signal.value >= 0 ? "up" : "down"}`}
          style={{ width: `${magnitude}%`, [signal.value >= 0 ? "left" : "right"]: "50%" }}
        />
      </div>
      <span className="signal__value">{signal.value >= 0 ? "+" : ""}{signal.value.toFixed(2)}</span>
      <span className="signal__weight">w{signal.weight.toFixed(2)}</span>
    </div>
  );
}

export function AdviceCard({
  advice,
  selected,
  onSelect,
}: {
  advice: Advice;
  selected: boolean;
  onSelect: (symbol: string) => void;
}) {
  return (
    <button
      type="button"
      className={`card ${selected ? "card--selected" : ""}`}
      onClick={() => onSelect(advice.symbol)}
    >
      <header className="card__head">
        <h2>{advice.symbol}</h2>
        <span className={`pill pill--${advice.direction}`}>{advice.direction}</span>
      </header>
      <p className="card__conviction">
        conviction <strong>{advice.conviction.toFixed(2)}</strong>
        <time dateTime={advice.timestamp}>{new Date(advice.timestamp).toLocaleString()}</time>
      </p>
      <div className="card__signals">
        {advice.signals.map((signal) => (
          <SignalBar key={signal.name} signal={signal} />
        ))}
      </div>
    </button>
  );
}
