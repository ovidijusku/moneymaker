import { useMemo, useState } from "react";

import { api } from "./api";
import { AdviceCard } from "./components/AdviceCard";
import { NewsList } from "./components/NewsList";
import { PriceChart } from "./components/PriceChart";
import { usePolling } from "./usePolling";

const REFRESH_MS = 30_000;
const WINDOW_HOURS = 24;

export default function App() {
  const [selected, setSelected] = useState<string | null>(null);

  const config = usePolling(() => api.config(), REFRESH_MS * 10, []);
  const advice = usePolling(() => api.latestAdvice(), REFRESH_MS, []);

  const symbol = selected ?? advice.data?.[0]?.symbol ?? config.data?.symbols[0] ?? null;

  const bars = usePolling(
    () => (symbol ? api.bars(symbol, WINDOW_HOURS) : Promise.resolve([])),
    REFRESH_MS,
    [symbol],
  );
  const news = usePolling(
    () => (symbol ? api.news(symbol, WINDOW_HOURS) : Promise.resolve([])),
    REFRESH_MS,
    [symbol],
  );

  const error = config.error ?? advice.error ?? bars.error ?? news.error;
  const cards = useMemo(() => advice.data ?? [], [advice.data]);

  return (
    <div className="app">
      <header className="app__head">
        <h1>moneymaker</h1>
        <span className="mode">
          {config.data ? `${config.data.trading_mode} — advisory only, no orders` : "connecting…"}
        </span>
      </header>

      {error && <p className="error">{error}</p>}

      <section className="cards">
        {cards.length === 0 && !advice.loading && (
          <p className="empty">
            No advice yet. The worker needs enough bar history before it forms an opinion.
          </p>
        )}
        {cards.map((item) => (
          <AdviceCard
            key={item.symbol}
            advice={item}
            selected={item.symbol === symbol}
            onSelect={setSelected}
          />
        ))}
      </section>

      <section className="panel">
        <h3>{symbol ?? "—"} · last {WINDOW_HOURS}h</h3>
        <PriceChart bars={bars.data ?? []} />
      </section>

      <section className="panel">
        <h3>Headlines</h3>
        <NewsList events={news.data ?? []} />
      </section>
    </div>
  );
}
