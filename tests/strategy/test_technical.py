from __future__ import annotations

from datetime import UTC, datetime

import pytest

from moneymaker.analysis.indicators import IndicatorSnapshot
from moneymaker.domain import Signal, SignalSource
from moneymaker.strategy.technical import TechnicalConfig, technical_signals

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _snapshot(
    *,
    ema_fast: float = 100.0,
    ema_slow: float = 100.0,
    rsi: float = 50.0,
    atr: float = 1.0,
    volume_ratio: float = 1.0,
) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        symbol="BTC/USD",
        timestamp=NOW,
        close=100.0,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        rsi=rsi,
        atr=atr,
        volume_ratio=volume_ratio,
    )


def _by_name(
    snapshot: IndicatorSnapshot, config: TechnicalConfig | None = None
) -> dict[str, Signal]:
    return {signal.name: signal for signal in technical_signals(snapshot, config)}


def test_emits_a_trend_and_a_momentum_signal() -> None:
    signals = technical_signals(_snapshot())

    assert {signal.name for signal in signals} == {"trend_ema", "momentum_rsi"}
    assert all(signal.source is SignalSource.TECHNICAL for signal in signals)
    assert all(signal.symbol == "BTC/USD" for signal in signals)


def test_fast_ema_above_slow_ema_is_bullish() -> None:
    trend = _by_name(_snapshot(ema_fast=100.5, ema_slow=100.0))["trend_ema"]

    assert trend.value > 0


def test_fast_ema_below_slow_ema_is_bearish() -> None:
    trend = _by_name(_snapshot(ema_fast=99.5, ema_slow=100.0))["trend_ema"]

    assert trend.value < 0


def test_trend_value_is_clamped_at_full_scale() -> None:
    trend = _by_name(_snapshot(ema_fast=200.0, ema_slow=100.0))["trend_ema"]

    assert trend.value == 1.0


def test_volume_surge_increases_the_trend_weight() -> None:
    config = TechnicalConfig()
    quiet = _by_name(_snapshot(ema_fast=100.5, volume_ratio=1.0), config)["trend_ema"]
    loud = _by_name(_snapshot(ema_fast=100.5, volume_ratio=2.0), config)["trend_ema"]

    assert loud.weight > quiet.weight
    assert "surge" in loud.evidence[1]
    assert "baseline" in quiet.evidence[1]


def test_trend_weight_never_exceeds_one() -> None:
    config = TechnicalConfig(trend_weight=1.0, volume_confirmation_bonus=1.0)
    trend = _by_name(_snapshot(ema_fast=100.5, volume_ratio=9.0), config)["trend_ema"]

    assert trend.weight == 1.0


def test_rsi_inside_the_neutral_band_says_nothing() -> None:
    momentum = _by_name(_snapshot(rsi=55.0))["momentum_rsi"]

    assert momentum.value == 0.0


def test_oversold_rsi_is_bullish() -> None:
    momentum = _by_name(_snapshot(rsi=25.0))["momentum_rsi"]

    assert momentum.value > 0


def test_overbought_rsi_is_bearish() -> None:
    momentum = _by_name(_snapshot(rsi=75.0))["momentum_rsi"]

    assert momentum.value < 0


def test_momentum_saturates_at_the_full_scale_distance() -> None:
    config = TechnicalConfig(rsi_neutral_band=10.0, rsi_full_scale=30.0)
    momentum = _by_name(_snapshot(rsi=5.0), config)["momentum_rsi"]

    assert momentum.value == 1.0


def test_trend_and_momentum_disagree_in_a_stretched_rally() -> None:
    signals = _by_name(_snapshot(ema_fast=101.0, ema_slow=100.0, rsi=85.0))

    assert signals["trend_ema"].value > 0
    assert signals["momentum_rsi"].value < 0


def test_signal_values_stay_within_the_signed_unit_range() -> None:
    for rsi in (0.0, 50.0, 100.0):
        for spread in (-10.0, 0.0, 10.0):
            for signal in technical_signals(_snapshot(ema_fast=100.0 + spread, rsi=rsi)):
                assert -1.0 <= signal.value <= 1.0


def test_neutral_band_must_sit_below_full_scale() -> None:
    with pytest.raises(ValueError, match="rsi_neutral_band"):
        TechnicalConfig(rsi_neutral_band=40.0, rsi_full_scale=30.0)
