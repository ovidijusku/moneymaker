import { useCallback, useEffect, useState } from "react";

interface Poll<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/** Re-fetches on an interval. The backend is a journal, so polling is enough. */
export function usePolling<T>(fetcher: () => Promise<T>, intervalMs: number, deps: unknown[]) {
  const [state, setState] = useState<Poll<T>>({ data: null, error: null, loading: true });

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fetcher, deps);

  useEffect(() => {
    let active = true;
    // Dropping the old value matters when deps change: showing the previous
    // symbol's trade plan next to a new symbol's name would be actively wrong.
    setState({ data: null, error: null, loading: true });

    const load = async () => {
      try {
        const data = await run();
        if (active) setState({ data, error: null, loading: false });
      } catch (error) {
        if (active) {
          setState({
            data: null,
            error: error instanceof Error ? error.message : "request failed",
            loading: false,
          });
        }
      }
    };

    void load();
    const timer = setInterval(load, intervalMs);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [run, intervalMs]);

  return state;
}
