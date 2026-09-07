"""Market data primitives."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator

from moneymaker.domain.types import Price, Quantity, Symbol, UtcDatetime


class Bar(BaseModel):
    """A closed OHLCV candle.

    Only closed bars enter the signal pipeline; acting on a forming bar's
    close is look-ahead bias.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: Symbol
    timestamp: UtcDatetime
    open: Price
    high: Price
    low: Price
    close: Price
    volume: Quantity
    trade_count: int = 0
    vwap: Price | None = None

    @model_validator(mode="after")
    def check_ohlc_consistency(self) -> Bar:
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if not (self.low <= self.open <= self.high):
            raise ValueError("open must fall within [low, high]")
        if not (self.low <= self.close <= self.high):
            raise ValueError("close must fall within [low, high]")
        return self


class Quote(BaseModel):
    """Top-of-book bid/ask snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: Symbol
    timestamp: UtcDatetime
    bid_price: Price
    ask_price: Price
    bid_size: Quantity = Decimal(0)
    ask_size: Quantity = Decimal(0)

    @model_validator(mode="after")
    def check_spread(self) -> Quote:
        if self.ask_price < self.bid_price:
            raise ValueError("ask_price must be >= bid_price")
        return self

    @property
    def mid_price(self) -> Price:
        return (self.bid_price + self.ask_price) / 2
