import { CandlestickSeries, createChart, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { Bar } from "../api";

const THEME = {
  layout: { background: { color: "#12151c" }, textColor: "#8b93a7" },
  grid: { vertLines: { color: "#1c212c" }, horzLines: { color: "#1c212c" } },
  timeScale: { borderColor: "#1c212c", timeVisible: true },
  rightPriceScale: { borderColor: "#1c212c" },
};

export function PriceChart({ bars }: { bars: Bar[] }) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ReturnType<IChartApi["addSeries"]> | null>(null);

  useEffect(() => {
    if (!container.current) return;
    chart.current = createChart(container.current, { ...THEME, autoSize: true });
    series.current = chart.current.addSeries(CandlestickSeries, {
      upColor: "#26a37b",
      downColor: "#d9534f",
      borderVisible: false,
      wickUpColor: "#26a37b",
      wickDownColor: "#d9534f",
    });
    return () => {
      chart.current?.remove();
      chart.current = null;
      series.current = null;
    };
  }, []);

  useEffect(() => {
    series.current?.setData(
      bars.map((bar) => ({
        time: (Date.parse(bar.timestamp) / 1000) as UTCTimestamp,
        open: Number(bar.open),
        high: Number(bar.high),
        low: Number(bar.low),
        close: Number(bar.close),
      })),
    );
  }, [bars]);

  return <div className="chart" ref={container} />;
}
