import type { PlanAction, TradePlan } from "../api";

const ACTION_LABELS: Record<PlanAction, string> = {
  buy: "Open a position",
  add: "Add to the position",
  reduce: "Trim the position",
  exit: "Close the position",
  hold: "Hold what you have",
  stand_aside: "No trade",
};

function money(value: string): string {
  return Number(value).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

function units(value: string): string {
  return Number(value).toLocaleString(undefined, { maximumSignificantDigits: 6 });
}

function pctFrom(price: string, level: string): string {
  const from = Number(price);
  if (!from) return "";
  return `${(((Number(level) - from) / from) * 100).toFixed(2)}%`;
}

export function TradePlanPanel({ plan }: { plan: TradePlan }) {
  const trading = Number(plan.quantity) > 0;

  return (
    <div className="plan">
      <div className={`plan-action ${plan.action}`}>{ACTION_LABELS[plan.action]}</div>

      {/* Levels show even when standing aside: knowing where the stop would go is
          how you judge whether the trade is worth taking at all. */}
      <dl className="plan-figures">
        {trading && (
          <div>
            <dt>Size</dt>
            <dd>
              {units(plan.quantity)} <span className="muted">{money(plan.notional)}</span>
            </dd>
          </div>
        )}
        <div>
          <dt>{trading ? "Entry" : "Price"}</dt>
          <dd>{money(plan.price)}</dd>
        </div>
        <div>
          <dt>Stop loss</dt>
          <dd className="down">
            {money(plan.stop)} <span className="muted">{pctFrom(plan.price, plan.stop)}</span>
          </dd>
        </div>
        <div>
          <dt>Target</dt>
          <dd className="up">
            {money(plan.target)} <span className="muted">{pctFrom(plan.price, plan.target)}</span>
          </dd>
        </div>
        {trading && (
          <div>
            <dt>At risk</dt>
            <dd>{money(plan.risk_amount)}</dd>
          </div>
        )}
      </dl>

      <div className="plan-holding">
        {Number(plan.held_quantity) > 0 ? (
          <>
            Holding {units(plan.held_quantity)} ({money(plan.held_value)}).
          </>
        ) : (
          <>
            No position in {plan.symbol}. Levels above are where a new one would sit at current
            volatility.
          </>
        )}
      </div>

      {plan.notes.length > 0 && (
        <ul className="plan-notes">
          {plan.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}

      <p className="disclaimer">
        Advisory only. Nothing here is sent to a broker &mdash; you place every order yourself.
      </p>
    </div>
  );
}
