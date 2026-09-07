"""Broker payloads are loosely typed strings and floats; the mappers are the
boundary where that becomes exact decimal arithmetic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from moneymaker.ingest.alpaca_account import fetch_portfolio, normalise, to_portfolio

NOW = datetime(2024, 1, 1, tzinfo=UTC)


@dataclass
class FakeAccount:
    equity: str = "100000"
    cash: str = "50000"


@dataclass
class FakeRawPosition:
    symbol: str = "BTCUSD"
    qty: str = "0.5"
    avg_entry_price: str = "60000"
    market_value: str = "31000"
    unrealized_pl: str | None = "1000"


@dataclass
class FakeTradingClient:
    account: FakeAccount = field(default_factory=FakeAccount)
    positions: list[FakeRawPosition] = field(default_factory=list)

    def get_account(self) -> FakeAccount:
        return self.account

    def get_all_positions(self) -> list[FakeRawPosition]:
        return list(self.positions)


def test_unslashed_broker_symbols_map_back_to_the_universe() -> None:
    """Alpaca reports positions as BTCUSD but quotes bars as BTC/USD."""
    assert normalise("BTCUSD") == "BTC/USD"
    assert normalise("btcusd") == "BTC/USD"
    assert normalise("BTC/USD") == "BTC/USD"


def test_unknown_symbols_pass_through_untouched() -> None:
    assert normalise("wat") == "WAT"


def test_floats_survive_as_exact_decimals() -> None:
    portfolio = to_portfolio(FakeAccount(equity="1.1"), [], now=NOW)

    assert portfolio.equity == Decimal("1.1")
    assert portfolio.positions == ()


def test_missing_unrealised_pnl_defaults_to_zero() -> None:
    portfolio = to_portfolio(FakeAccount(), [FakeRawPosition(unrealized_pl=None)], now=NOW)

    assert portfolio.positions[0].unrealised_pnl == Decimal(0)


async def test_fetch_builds_a_full_snapshot() -> None:
    client = FakeTradingClient(positions=[FakeRawPosition()])

    portfolio = await fetch_portfolio(client, now=NOW)

    assert portfolio.timestamp == NOW
    assert portfolio.equity == Decimal("100000")
    assert portfolio.cash == Decimal("50000")
    position = portfolio.positions[0]
    assert position.symbol == "BTC/USD"
    assert position.quantity == Decimal("0.5")
    assert position.market_value == Decimal("31000")


async def test_lookup_ignores_flat_positions() -> None:
    client = FakeTradingClient(positions=[FakeRawPosition(qty="0", market_value="0")])

    portfolio = await fetch_portfolio(client, now=NOW)

    assert portfolio.position_for("BTC/USD") is None
    assert portfolio.exposure == Decimal(0)


async def test_exposure_sums_open_positions() -> None:
    client = FakeTradingClient(
        positions=[
            FakeRawPosition(),
            FakeRawPosition(symbol="ETHUSD", market_value="2000"),
        ]
    )

    portfolio = await fetch_portfolio(client, now=NOW)

    assert portfolio.exposure == Decimal("33000")
    assert portfolio.position_for("ETH/USD") is not None
