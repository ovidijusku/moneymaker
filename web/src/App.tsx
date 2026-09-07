import { useState } from "react";

import { api, type StreamEvent } from "./api";
import { AdviceCard } from "./components/AdviceCard";
import { EventStream } from "./components/EventStream";
import { PriceChart } from "./components/PriceChart";
import { TradePlanPanel } from "./components/TradePlanPanel";
import { usePolling } from "./usePolling";

const REFRESH_MS = 30_000;
const WINDOW_HOURS = 24;

function money(value: string): string {
  return Number(value).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

export default function App() {
  const [selected, setSelected] = useState<StreamEvent | null>(null);

  const config = usePolling(() => api.config(), REFRESH_MS * 10, []);
  const events = usePolling(() => api.events(WINDOW_HOURS), REFRESH_MS, []);
  const advice = usePolling(() => api.latestAdvice(), REFRESH_MS, []);
  const portfolio = usePolling(() => api.portfolio(), REFRESH_MS, []);

  const symbol = selected?.symbols[0] ?? null;

  const plan = usePolling(
    () => (symbol ? api.plan(symbol) : Promise.resolve(null)),
    REFRESH_MS,
    [symbol],
  );
  const bars = usePolling(
    () => (symbol ? api.bars(symbol, WINDOW_HOURS) : Promise.resolve([])),
    REFRESH_MS,
    [symbol],
  );

  // A 404/409 from /plan means "not enough data yet", not a broken app, so it
  // is reported inside the detail panel rather than as a page-level error.
  const error = config.error ?? events.error ?? advice.error ?? portfolio.error;
  const current = advice.data?.find((item) => item.symbol === symbol) ?? null;
  const account = portfolio.data;

  return (
    <div className="app">
      <header className="app__head">
        <div>
          <h1>moneymaker</h1>
          <span className="mode">
            {config.data
              ? `${config.data.symbols.length} pairs · advisory only, spot long`
              : "connecting…"}
          </span>
        </div>
        {account && (
          <dl className="account">
            <div>
              <dt>Equity</dt>
              <dd>{money(account.equity)}</dd>
            </div>
            <div>
              <dt>Cash</dt>
              <dd>{money(account.cash)}</dd>
            </div>
            <div>
              <dt>Positions</dt>
              <dd>{account.positions.length}</dd>
            </div>
          </dl>
        )}
      </header>

      {error && <p className="error">{error}</p>}

      <div className="layout">
        <section className="panel stream-panel">
          <h3>
            Event stream · last {WINDOW_HOURS}h
            {events.data && <span className="muted"> · {events.data.length} items</span>}
          </h3>
          <EventStream
            events={events.data ?? []}
            selectedId={selected?.id ?? null}
            onSelect={setSelected}
          />
        </section>

        <section className="panel detail-panel">
          {!selected ? (
            <p className="empty">Pick an event to see how much to buy and where the stop goes.</p>
          ) : (
            <>
              <h3>
                {selected.names.join(", ") || selected.symbols.join(", ")}
                {selected.url && (
                  <a className="link" href={selected.url} target="_blank" rel="noreferrer">
                    source
                  </a>
                )}
              </h3>

              {plan.data ? (
                <TradePlanPanel plan={plan.data} />
              ) : plan.error ? (
                <p className="empty">{plan.error}</p>
              ) : (
                <p className="empty">Sizing…</p>
              )}

              {current && <AdviceCard advice={current} selected onSelect={() => undefined} />}

              <PriceChart bars={bars.data ?? []} />
            </>
          )}
        </section>
      </div>
    </div>
  );
}
