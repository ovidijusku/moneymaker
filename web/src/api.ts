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

export interface Asset {
  symbol: string;
  name: string;
  tickers: string[];
  aliases: string[];
}

export interface Config {
  trading_mode: string;
  symbols: string[];
  executes_orders: boolean;
  advice_poll_seconds: number;
  assets: Asset[];
  shorting_available: boolean;
}

export type EventKind = "news" | "social" | "advice";

export interface StreamEvent {
  id: string;
  kind: EventKind;
  timestamp: string;
  symbols: string[];
  names: string[];
  title: string;
  summary: string;
  source: string;
  url: string | null;
  direction: Direction | null;
  conviction: number | null;
}

export interface Position {
  symbol: string;
  quantity: string;
  average_entry: string;
  market_value: string;
  unrealised_pnl: string;
}

export interface Portfolio {
  timestamp: string;
  equity: string;
  cash: string;
  positions: Position[];
}

export type PlanAction = "buy" | "add" | "reduce" | "exit" | "hold" | "stand_aside";

export interface TradePlan {
  symbol: string;
  timestamp: string;
  action: PlanAction;
  direction: Direction;
  conviction: number;
  price: string;
  stop: string;
  target: string;
  quantity: string;
  notional: string;
  risk_amount: string;
  held_quantity: string;
  held_value: string;
  notes: string[];
  shortable: boolean;
}

/** Thrown for non-2xx so callers can distinguish "not ready yet" from a real fault. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
  }
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`);
  if (!response.ok) {
    let detail = `${path} failed: ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // A non-JSON error body is still an error; the status carries the meaning.
    }
    throw new ApiError(response.status, detail);
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
  events: (hours = 24, limit = 100) => get<StreamEvent[]>(`/events?hours=${hours}&limit=${limit}`),
  portfolio: () => get<Portfolio | null>("/portfolio"),
  plan: (symbol: string) => get<TradePlan>(`/plan?symbol=${encodeURIComponent(symbol)}`),
};
