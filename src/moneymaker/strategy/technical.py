"""Technical signals derived from an indicator snapshot.

Two signals with deliberately opposed temperaments: the EMA spread follows
trend, RSI fades extremes. They disagree at turning points, and that
disagreement is the point -- it keeps conviction low exactly where a single
indicator would be most confidently wrong.

ATR is not emitted as a signal. Volatility has no direction; it belongs in
position sizing and in the conviction damping applied by the composite scorer.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, model_validator

from moneymaker.analysis.indicators import IndicatorSnapshot
from moneymaker.domain import Signal, SignalSource
from moneymaker.domain.types import clamp


class TechnicalConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    #: EMA spread, as a fraction of price, that counts as full conviction.
    trend_full_scale: float = Field(default=0.01, gt=0.0)
    #: RSI distance from 50 that still reads as noise.
    rsi_neutral_band: float = Field(default=10.0, ge=0.0, lt=50.0)
    #: RSI distance from 50 that counts as full conviction.
    rsi_full_scale: float = Field(default=30.0, gt=0.0, le=50.0)
    #: Volume multiple above baseline that confirms a trend.
    volume_surge: float = Field(default=1.5, ge=1.0)
    trend_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    momentum_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    #: How much a confirmed volume surge lifts the trend signal's weight.
    volume_confirmation_bonus: float = Field(default=0.25, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def check_rsi_bands(self) -> TechnicalConfig:
        if self.rsi_neutral_band >= self.rsi_full_scale:
            raise ValueError("rsi_neutral_band must be below rsi_full_scale")
        return self


def _trend_signal(
    snapshot: IndicatorSnapshot,
    config: TechnicalConfig,
) -> Signal:
    value = clamp(snapshot.ema_spread / config.trend_full_scale)
    confirmed = snapshot.volume_ratio >= config.volume_surge
    weight = config.trend_weight
    if confirmed:
        weight = min(1.0, weight * (1.0 + config.volume_confirmation_bonus))
    evidence = [
        f"ema_spread={snapshot.ema_spread:+.4%}",
        f"volume_ratio={snapshot.volume_ratio:.2f}" + (" (surge)" if confirmed else " (baseline)"),
    ]
    return Signal(
        symbol=snapshot.symbol,
        timestamp=snapshot.timestamp,
        source=SignalSource.TECHNICAL,
        name="trend_ema",
        value=value,
        weight=weight,
        evidence=tuple(evidence),
    )


def _momentum_signal(
    snapshot: IndicatorSnapshot,
    config: TechnicalConfig,
) -> Signal:
    # Positive distance means oversold, which reads as a buy.
    distance = 50.0 - snapshot.rsi
    span = config.rsi_full_scale - config.rsi_neutral_band
    magnitude = clamp((abs(distance) - config.rsi_neutral_band) / span, 0.0, 1.0)
    value = math.copysign(magnitude, distance) if magnitude else 0.0
    return Signal(
        symbol=snapshot.symbol,
        timestamp=snapshot.timestamp,
        source=SignalSource.TECHNICAL,
        name="momentum_rsi",
        value=value,
        weight=config.momentum_weight,
        evidence=(f"rsi={snapshot.rsi:.1f}",),
    )


def technical_signals(
    snapshot: IndicatorSnapshot,
    config: TechnicalConfig | None = None,
) -> tuple[Signal, ...]:
    settings = config or TechnicalConfig()
    return (
        _trend_signal(snapshot, settings),
        _momentum_signal(snapshot, settings),
    )
