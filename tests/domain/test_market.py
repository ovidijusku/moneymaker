from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from moneymaker.domain import Bar, Quote

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_bar(**overrides: object) -> Bar:
    defaults: dict[str, object] = {
        "symbol": "btc/usd",
        "timestamp": NOW,
        "open": Decimal("100"),
        "high": Decimal("110"),
        "low": Decimal("90"),
        "close": Decimal("105"),
        "volume": Decimal("3.5"),
    }
    return Bar(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_bar_normalises_symbol_to_uppercase() -> None:
    assert make_bar().symbol == "BTC/USD"


def test_bar_is_immutable() -> None:
    bar = make_bar()

    with pytest.raises(ValidationError):
        bar.close = Decimal("1")


def test_bar_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_bar(timestamp=datetime(2026, 1, 1, 12, 0))  # noqa: DTZ001


def test_bar_converts_timestamp_to_utc() -> None:
    from datetime import timedelta, timezone

    bar = make_bar(timestamp=datetime(2026, 1, 1, 14, 0, tzinfo=timezone(timedelta(hours=2))))

    assert bar.timestamp == NOW


def test_bar_rejects_high_below_low() -> None:
    with pytest.raises(ValidationError, match="high must be >= low"):
        make_bar(high=Decimal("80"), low=Decimal("90"))


@pytest.mark.parametrize("field", ["open", "close"])
def test_bar_rejects_price_outside_range(field: str) -> None:
    with pytest.raises(ValidationError, match="within \\[low, high\\]"):
        make_bar(**{field: Decimal("500")})


def test_bar_rejects_negative_volume() -> None:
    with pytest.raises(ValidationError):
        make_bar(volume=Decimal("-1"))


def test_bar_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        make_bar(sneaky=True)


def test_bar_rejects_blank_symbol() -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        make_bar(symbol="   ")


def test_quote_mid_price() -> None:
    quote = Quote(
        symbol="ETH/USD",
        timestamp=NOW,
        bid_price=Decimal("100"),
        ask_price=Decimal("102"),
    )

    assert quote.mid_price == Decimal("101")


def test_quote_rejects_crossed_book() -> None:
    with pytest.raises(ValidationError, match="ask_price must be >= bid_price"):
        Quote(
            symbol="ETH/USD",
            timestamp=NOW,
            bid_price=Decimal("102"),
            ask_price=Decimal("100"),
        )
