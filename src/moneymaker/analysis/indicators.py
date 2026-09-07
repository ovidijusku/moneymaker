"""Technical indicators computed over a trailing window of bars.

talipp is incremental, but this module deliberately recomputes from a bounded
window instead of holding long-lived indicator objects: the bars already live in
the database, so a pure function replays identically in live polling and in a
backtest, and needs no state to be invalidated when a poll fails.

Indicator maths runs in float. Decimal matters for what we persist and settle,
not for a moving average.
"""

from __future__ import annotations

from collections.abc import Sequence
from statistics import fmean

from pydantic import BaseModel, ConfigDict, Field, model_validator
from talipp.indicators import ATR, EMA, RSI
from talipp.ohlcv import OHLCV

from moneymaker.domain import Bar
from moneymaker.domain.types import Symbol, UtcDatetime


class IndicatorConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ema_fast: int = Field(default=12, ge=2)
    ema_slow: int = Field(default=26, ge=3)
    rsi_period: int = Field(default=14, ge=2)
    atr_period: int = Field(default=14, ge=2)
    volume_lookback: int = Field(default=20, ge=2)

    @model_validator(mode="after")
    def check_ema_ordering(self) -> IndicatorConfig:
        if self.ema_fast >= self.ema_slow:
            raise ValueError("ema_fast must be shorter than ema_slow")
        return self

    @property
    def required_history(self) -> int:
        """Bars needed before every indicator has warmed up."""
        return (
            max(
                self.ema_slow,
                self.rsi_period,
                self.atr_period,
                self.volume_lookback,
            )
            + 1
        )


class IndicatorSnapshot(BaseModel):
    """Indicator state as of the most recent bar."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: Symbol
    timestamp: UtcDatetime
    close: float
    ema_fast: float
    ema_slow: float
    rsi: float = Field(ge=0.0, le=100.0)
    atr: float = Field(ge=0.0)
    #: Latest volume over its trailing baseline; 1.0 means an ordinary bar.
    volume_ratio: float = Field(ge=0.0)

    @property
    def ema_spread(self) -> float:
        """Fast-minus-slow EMA as a fraction of the slow EMA."""
        return (self.ema_fast - self.ema_slow) / self.ema_slow

    @property
    def volatility(self) -> float:
        """ATR as a fraction of price, so it compares across symbols."""
        return self.atr / self.close if self.close else 0.0


def _last(values: Sequence[float | None]) -> float | None:
    return values[-1] if values else None


def _to_ohlcv(bar: Bar) -> OHLCV:
    return OHLCV(
        float(bar.open),
        float(bar.high),
        float(bar.low),
        float(bar.close),
        float(bar.volume),
        bar.timestamp,
    )


def _volume_ratio(bars: Sequence[Bar], lookback: int) -> float:
    baseline_bars = bars[-lookback - 1 : -1]
    baseline = fmean(float(bar.volume) for bar in baseline_bars)
    # A flat-zero baseline carries no information, so report "ordinary".
    return float(bars[-1].volume) / baseline if baseline > 0 else 1.0


def _check_window(bars: Sequence[Bar]) -> None:
    symbols = {bar.symbol for bar in bars}
    if len(symbols) > 1:
        raise ValueError(f"bars must share one symbol, got {sorted(symbols)}")
    timestamps = [bar.timestamp for bar in bars]
    if timestamps != sorted(timestamps):
        raise ValueError("bars must be in ascending timestamp order")


def compute_indicators(
    bars: Sequence[Bar],
    config: IndicatorConfig | None = None,
) -> IndicatorSnapshot | None:
    """Return the snapshot at the last bar, or None while indicators warm up."""
    settings = config or IndicatorConfig()
    if len(bars) < settings.required_history:
        return None
    _check_window(bars)

    closes = [float(bar.close) for bar in bars]
    candles = [_to_ohlcv(bar) for bar in bars]

    ema_fast = _last(EMA(settings.ema_fast, closes))
    ema_slow = _last(EMA(settings.ema_slow, closes))
    rsi = _last(RSI(settings.rsi_period, closes))
    atr = _last(ATR(settings.atr_period, candles))
    if ema_fast is None or ema_slow is None or rsi is None or atr is None:
        return None

    latest = bars[-1]
    return IndicatorSnapshot(
        symbol=latest.symbol,
        timestamp=latest.timestamp,
        close=float(latest.close),
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        rsi=rsi,
        atr=atr,
        volume_ratio=_volume_ratio(bars, settings.volume_lookback),
    )
