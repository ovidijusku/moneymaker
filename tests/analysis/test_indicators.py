from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from moneymaker.analysis.indicators import IndicatorConfig, compute_indicators
from moneymaker.domain import Bar

START = datetime(2026, 1, 1, tzinfo=UTC)
CONFIG = IndicatorConfig(
    ema_fast=3,
    ema_slow=5,
    rsi_period=3,
    atr_period=3,
    volume_lookback=3,
)


def _bar(index: int, close: float, *, volume: float = 10.0, symbol: str = "BTC/USD") -> Bar:
    price = Decimal(str(close))
    return Bar(
        symbol=symbol,
        timestamp=START + timedelta(minutes=index),
        open=price,
        high=price + Decimal("1"),
        low=price - Decimal("1"),
        close=price,
        volume=Decimal(str(volume)),
    )


def _series(closes: list[float], volumes: list[float] | None = None) -> list[Bar]:
    sizes = volumes or [10.0] * len(closes)
    return [_bar(i, close, volume=sizes[i]) for i, close in enumerate(closes)]


def test_returns_none_until_enough_history_is_available() -> None:
    bars = _series([100.0] * (CONFIG.required_history - 1))

    assert compute_indicators(bars, CONFIG) is None


def test_produces_snapshot_once_warmed_up() -> None:
    bars = _series([100.0 + i for i in range(CONFIG.required_history)])

    snapshot = compute_indicators(bars, CONFIG)

    assert snapshot is not None
    assert snapshot.symbol == "BTC/USD"
    assert snapshot.timestamp == bars[-1].timestamp
    assert snapshot.close == float(bars[-1].close)


def test_rising_market_puts_fast_ema_above_slow_ema() -> None:
    bars = _series([100.0 + 2 * i for i in range(20)])

    snapshot = compute_indicators(bars, CONFIG)

    assert snapshot is not None
    assert snapshot.ema_fast > snapshot.ema_slow
    assert snapshot.ema_spread > 0


def test_falling_market_puts_fast_ema_below_slow_ema() -> None:
    bars = _series([200.0 - 2 * i for i in range(20)])

    snapshot = compute_indicators(bars, CONFIG)

    assert snapshot is not None
    assert snapshot.ema_spread < 0


def test_rsi_is_high_in_an_uptrend_and_low_in_a_downtrend() -> None:
    rising = compute_indicators(_series([100.0 + i for i in range(20)]), CONFIG)
    falling = compute_indicators(_series([200.0 - i for i in range(20)]), CONFIG)

    assert rising is not None
    assert falling is not None
    assert rising.rsi > 70
    assert falling.rsi < 30


def test_volume_ratio_measures_the_latest_bar_against_its_baseline() -> None:
    volumes = [10.0] * 19 + [30.0]
    bars = _series([100.0] * 20, volumes)

    snapshot = compute_indicators(bars, CONFIG)

    assert snapshot is not None
    assert snapshot.volume_ratio == pytest.approx(3.0)


def test_volume_ratio_excludes_the_latest_bar_from_its_own_baseline() -> None:
    # If the surge bar were included, the ratio would be diluted below 3.0.
    volumes = [10.0] * 19 + [30.0]
    snapshot = compute_indicators(_series([100.0] * 20, volumes), CONFIG)

    assert snapshot is not None
    assert snapshot.volume_ratio > 1.0


def test_zero_volume_baseline_reports_an_ordinary_bar() -> None:
    volumes = [0.0] * 20
    snapshot = compute_indicators(_series([100.0] * 20, volumes), CONFIG)

    assert snapshot is not None
    assert snapshot.volume_ratio == 1.0


def test_volatility_normalises_atr_by_price() -> None:
    snapshot = compute_indicators(_series([100.0] * 20), CONFIG)

    assert snapshot is not None
    assert snapshot.volatility == pytest.approx(snapshot.atr / snapshot.close)


def test_mixed_symbols_are_rejected() -> None:
    bars = _series([100.0] * 20)
    bars[5] = _bar(5, 100.0, symbol="ETH/USD")

    with pytest.raises(ValueError, match="one symbol"):
        compute_indicators(bars, CONFIG)


def test_out_of_order_bars_are_rejected() -> None:
    bars = _series([100.0] * 20)
    shuffled = [*bars[:10], bars[15], *bars[10:15], *bars[16:]]

    with pytest.raises(ValueError, match="ascending"):
        compute_indicators(shuffled, CONFIG)


def test_default_config_is_usable_without_arguments() -> None:
    bars = _series([100.0 + i for i in range(60)])

    assert compute_indicators(bars) is not None


def test_ema_fast_must_be_shorter_than_ema_slow() -> None:
    with pytest.raises(ValueError, match="ema_fast"):
        IndicatorConfig(ema_fast=26, ema_slow=12)
