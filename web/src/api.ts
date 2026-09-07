export type Direction = "buy" | "sell" | "hold";

export interface Signal {
  symbol: string;
  timestamp: string;
  source: "technical" | "news" | "social";
  name: string;
  value: number;
  weight: number;
  evidence: string[];
}

export interface Advice {
  symbol: string;
  timestamp: string;
  direction: Direction;
  conviction: number;
  rationale: string;
  signals: Signal[];
}

/** Prices arrive as strings so the backend never rounds a Decimal into a float. */
export interface Bar {
  symbol: string;
  timestamp: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

export interface NewsEvent {
  id: string;
  feed: string;
  url: string;
  title: string;
  published_at: string;
  symbols: string[];
}

export interface Config {
  trading_mode: string;
  symbols: string[];
  executes_orders: boolean;
  advice_poll_seconds: number;
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`);
  if (!response.ok) {
    throw new Error(`${path} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  config: () => get<Config>("/config"),
  latestAdvice: () => get<Advice[]>("/advice/latest"),
  bars: (symbol: string, hours = 24) =>
    get<Bar[]>(`/bars?symbol=${encodeURIComponent(symbol)}&hours=${hours}`),
  news: (symbol: string, hours = 24) =>
    get<NewsEvent[]>(`/news?symbol=${encodeURIComponent(symbol)}&hours=${hours}`),
};
