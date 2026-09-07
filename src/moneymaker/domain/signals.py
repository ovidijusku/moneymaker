"""Signals and the advisory output of the pipeline."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from moneymaker.domain.types import SignedUnit, Symbol, UnitInterval, UtcDatetime


class SignalSource(StrEnum):
    TECHNICAL = "technical"
    NEWS = "news"
    SOCIAL = "social"


class Direction(StrEnum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class Signal(BaseModel):
    """One scored input. `value` is directional; `weight` is its blend share."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: Symbol
    timestamp: UtcDatetime
    source: SignalSource
    name: str
    value: SignedUnit
    weight: UnitInterval = 1.0
    evidence: tuple[str, ...] = ()


class Advice(BaseModel):
    """A recommendation shown to the user. Never auto-executed in advisory mode."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: Symbol
    timestamp: UtcDatetime
    direction: Direction
    conviction: UnitInterval
    rationale: str
    signals: tuple[Signal, ...] = Field(default=())

    @property
    def is_actionable(self) -> bool:
        return self.direction is not Direction.HOLD and self.conviction > 0.0
