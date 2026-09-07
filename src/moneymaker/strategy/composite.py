"""Blending signals into a single piece of advice.

Sources are weighted by how much they have historically been worth, not by how
loud they are: technical signals dominate, social sits at the bottom because
crypto influencer posts are heavily contaminated by paid promotion. Phase 4's
advice journal is what should eventually move these numbers.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from moneymaker.domain import Advice, Direction, Signal, SignalSource
from moneymaker.domain.types import clamp


class CompositeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    technical_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    news_weight: float = Field(default=0.25, ge=0.0, le=1.0)
    social_weight: float = Field(default=0.15, ge=0.0, le=1.0)
    #: Blended score below this is noise, and noise is a HOLD.
    action_threshold: float = Field(default=0.2, ge=0.0, lt=1.0)
    #: ATR/price above this starts cutting conviction; whipsaws eat edge.
    volatility_ceiling: float = Field(default=0.05, gt=0.0)

    @model_validator(mode="after")
    def check_weights(self) -> CompositeConfig:
        if self.technical_weight + self.news_weight + self.social_weight <= 0:
            raise ValueError("at least one source weight must be positive")
        return self

    def weight_for(self, source: SignalSource) -> float:
        return {
            SignalSource.TECHNICAL: self.technical_weight,
            SignalSource.NEWS: self.news_weight,
            SignalSource.SOCIAL: self.social_weight,
        }[source]


def blend(signals: Sequence[Signal], config: CompositeConfig) -> float:
    """Weighted mean of signal values in [-1, 1]; 0.0 when nothing has weight."""
    total = 0.0
    weighted = 0.0
    for signal in signals:
        weight = config.weight_for(signal.source) * signal.weight
        total += weight
        weighted += weight * signal.value
    return clamp(weighted / total) if total > 0 else 0.0


def _damping(volatility: float | None, ceiling: float) -> float:
    if volatility is None or volatility <= ceiling:
        return 1.0
    return clamp(ceiling / volatility, 0.0, 1.0)


def _direction(score: float, threshold: float) -> Direction:
    if score >= threshold:
        return Direction.BUY
    if score <= -threshold:
        return Direction.SELL
    return Direction.HOLD


def _rationale(direction: Direction, score: float, signals: Sequence[Signal]) -> str:
    parts = [f"{signal.name}={signal.value:+.2f}" for signal in signals]
    detail = ", ".join(parts) if parts else "no signals"
    return f"{direction.value} on blended score {score:+.2f} ({detail})"


def build_advice(
    *,
    symbol: str,
    timestamp: datetime,
    signals: Sequence[Signal],
    volatility: float | None = None,
    config: CompositeConfig | None = None,
) -> Advice:
    settings = config or CompositeConfig()
    score = blend(signals, settings)
    direction = _direction(score, settings.action_threshold)
    conviction = abs(score) * _damping(volatility, settings.volatility_ceiling)
    return Advice(
        symbol=symbol,
        timestamp=timestamp,
        direction=direction,
        conviction=(clamp(conviction, 0.0, 1.0) if direction is not Direction.HOLD else 0.0),
        rationale=_rationale(direction, score, signals),
        signals=tuple(signals),
    )
