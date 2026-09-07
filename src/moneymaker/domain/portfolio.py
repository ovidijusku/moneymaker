"""What we actually hold. Sizing is meaningless without it."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from moneymaker.domain.types import Price, Symbol, UtcDatetime


class Position(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: Symbol
    quantity: Decimal
    average_entry: Price
    market_value: Decimal
    unrealised_pnl: Decimal = Decimal(0)

    @property
    def is_open(self) -> bool:
        return self.quantity != 0


class Portfolio(BaseModel):
    """A snapshot of the brokerage account at a point in time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: UtcDatetime
    equity: Decimal
    cash: Decimal
    positions: tuple[Position, ...] = Field(default=())

    def position_for(self, symbol: str) -> Position | None:
        return next((p for p in self.positions if p.symbol == symbol and p.is_open), None)

    @property
    def exposure(self) -> Decimal:
        return sum((p.market_value for p in self.positions), Decimal(0))
