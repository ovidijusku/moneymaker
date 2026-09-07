"""Alpaca crypto bar ingestion."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame

from moneymaker.domain import Bar


class AlpacaBar(Protocol):
    """The subset of ``alpaca.data.models.Bar`` we consume."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: float | None
    vwap: float | None


class CryptoBarsClient(Protocol):
    def get_crypto_bars(self, request_params: Any) -> Any: ...


def _to_decimal(value: float | int | str) -> Decimal:
    """Route through str: Alpaca hands us floats, and Decimal(float) would
    preserve the binary rounding error rather than the intended value."""
    return Decimal(str(value))


def to_bar(raw: AlpacaBar) -> Bar:
    timestamp = raw.timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return Bar(
        symbol=raw.symbol,
        timestamp=timestamp,
        open=_to_decimal(raw.open),
        high=_to_decimal(raw.high),
        low=_to_decimal(raw.low),
        close=_to_decimal(raw.close),
        volume=_to_decimal(raw.volume),
        trade_count=int(raw.trade_count or 0),
        vwap=None if raw.vwap is None else _to_decimal(raw.vwap),
    )


def to_bars(data: Mapping[str, Sequence[AlpacaBar]]) -> tuple[Bar, ...]:
    return tuple(
        sorted(
            (to_bar(raw) for raws in data.values() for raw in raws),
            key=lambda bar: (bar.symbol, bar.timestamp),
        )
    )


async def backfill(
    client: CryptoBarsClient,
    symbols: Sequence[str],
    *,
    start: datetime,
    end: datetime | None = None,
    timeframe: TimeFrame | None = None,
) -> tuple[Bar, ...]:
    """Fetch historical bars. The SDK is synchronous, so it runs off-loop."""
    # The SDK stores request datetimes naive, so normalise to UTC before handing over.
    request = CryptoBarsRequest(
        symbol_or_symbols=list(symbols),
        timeframe=timeframe or TimeFrame.Minute,
        start=start.astimezone(UTC),
        end=None if end is None else end.astimezone(UTC),
    )
    barset = await asyncio.to_thread(client.get_crypto_bars, request)
    return to_bars(barset.data)
