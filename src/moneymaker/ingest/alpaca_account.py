"""Read the brokerage account. Read-only by construction: nothing here places orders."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from moneymaker.domain import Portfolio, Position
from moneymaker.universe import DEFAULT_SYMBOLS

# Alpaca reports crypto positions unslashed ("BTCUSD"), but quotes bars slashed.
_BY_COMPACT = {symbol.replace("/", ""): symbol for symbol in DEFAULT_SYMBOLS}


class TradingAccount(Protocol):
    def get_account(self) -> Any: ...
    def get_all_positions(self) -> list[Any]: ...


def _decimal(value: Any, default: str = "0") -> Decimal:
    """Alpaca returns numbers as strings or floats; route both through str()."""
    if value is None:
        return Decimal(default)
    return Decimal(str(value))


def normalise(symbol: str) -> str:
    compact = symbol.strip().upper()
    return _BY_COMPACT.get(compact, compact)


def to_position(raw: Any) -> Position:
    return Position(
        symbol=normalise(str(raw.symbol)),
        quantity=_decimal(raw.qty),
        average_entry=_decimal(raw.avg_entry_price),
        market_value=_decimal(raw.market_value),
        unrealised_pnl=_decimal(getattr(raw, "unrealized_pl", None)),
    )


def to_portfolio(account: Any, positions: list[Any], *, now: datetime) -> Portfolio:
    return Portfolio(
        timestamp=now,
        equity=_decimal(account.equity),
        cash=_decimal(account.cash),
        positions=tuple(to_position(raw) for raw in positions),
    )


async def fetch_portfolio(client: TradingAccount, *, now: datetime | None = None) -> Portfolio:
    account, positions = await asyncio.gather(
        asyncio.to_thread(client.get_account),
        asyncio.to_thread(client.get_all_positions),
    )
    return to_portfolio(account, positions, now=now or datetime.now(tz=UTC))
