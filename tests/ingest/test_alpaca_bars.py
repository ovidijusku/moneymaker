from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from moneymaker.ingest.alpaca_bars import backfill, to_bar, to_bars

START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@dataclass
class FakeAlpacaBar:
    symbol: str = "BTC/USD"
    timestamp: datetime = START
    open: float = 100.1
    high: float = 110.0
    low: float = 90.0
    close: float = 105.0
    volume: float = 3.5
    trade_count: float | None = 12.0
    vwap: float | None = 101.25


@dataclass
class FakeBarSet:
    data: dict[str, list[FakeAlpacaBar]]


class FakeClient:
    def __init__(self, barset: FakeBarSet) -> None:
        self.barset = barset
        self.requests: list[Any] = []

    def get_crypto_bars(self, request_params: Any) -> FakeBarSet:
        self.requests.append(request_params)
        return self.barset


def test_float_prices_convert_without_binary_rounding_error() -> None:
    bar = to_bar(FakeAlpacaBar(open=0.1, low=0.05, high=0.2, close=0.15))

    assert bar.open == Decimal("0.1")
    assert bar.open != Decimal(0.1)  # noqa: RUF032 -- the point of the test


def test_trade_count_is_coerced_to_int() -> None:
    assert to_bar(FakeAlpacaBar(trade_count=12.0)).trade_count == 12


def test_missing_trade_count_defaults_to_zero() -> None:
    assert to_bar(FakeAlpacaBar(trade_count=None)).trade_count == 0


def test_missing_vwap_stays_none() -> None:
    assert to_bar(FakeAlpacaBar(vwap=None)).vwap is None


def test_naive_timestamps_are_treated_as_utc() -> None:
    naive = datetime(2026, 1, 1, 12, 0)  # noqa: DTZ001

    assert to_bar(FakeAlpacaBar(timestamp=naive)).timestamp == START


def test_inconsistent_ohlc_from_upstream_is_rejected() -> None:
    with pytest.raises(ValueError, match="high must be >= low"):
        to_bar(FakeAlpacaBar(high=50.0, low=90.0))


def test_to_bars_flattens_and_sorts_by_symbol_then_time() -> None:
    data = {
        "ETH/USD": [FakeAlpacaBar(symbol="ETH/USD", timestamp=START)],
        "BTC/USD": [
            FakeAlpacaBar(timestamp=START + timedelta(minutes=1)),
            FakeAlpacaBar(timestamp=START),
        ],
    }

    bars = to_bars(data)

    assert [(bar.symbol, bar.timestamp) for bar in bars] == [
        ("BTC/USD", START),
        ("BTC/USD", START + timedelta(minutes=1)),
        ("ETH/USD", START),
    ]


async def test_backfill_requests_the_given_window_and_symbols() -> None:
    client = FakeClient(FakeBarSet({"BTC/USD": [FakeAlpacaBar()]}))
    end = START + timedelta(hours=1)

    bars = await backfill(client, ["BTC/USD"], start=START, end=end)

    assert len(bars) == 1
    request = client.requests[0]
    assert request.symbol_or_symbols == ["BTC/USD"]
    assert request.start == START.replace(tzinfo=None)
    assert request.end == end.replace(tzinfo=None)


async def test_backfill_converts_non_utc_window_to_utc() -> None:
    client = FakeClient(FakeBarSet({}))
    berlin = timezone(timedelta(hours=2))

    await backfill(client, ["BTC/USD"], start=datetime(2026, 1, 1, 14, 0, tzinfo=berlin))

    assert client.requests[0].start == datetime(2026, 1, 1, 12, 0)  # noqa: DTZ001


async def test_backfill_returns_empty_when_upstream_has_no_data() -> None:
    client = FakeClient(FakeBarSet({}))

    assert await backfill(client, ["BTC/USD"], start=START) == ()
