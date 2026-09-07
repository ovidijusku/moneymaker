from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from moneymaker.domain import Advice, Direction, Signal, SignalSource

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_signal(**overrides: object) -> Signal:
    defaults: dict[str, object] = {
        "symbol": "BTC/USD",
        "timestamp": NOW,
        "source": SignalSource.TECHNICAL,
        "name": "ema_cross",
        "value": 0.6,
    }
    return Signal(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_signal_defaults_to_full_weight() -> None:
    assert make_signal().weight == 1.0


@pytest.mark.parametrize("value", [-1.5, 1.5])
def test_signal_rejects_value_outside_signed_unit(value: float) -> None:
    with pytest.raises(ValidationError):
        make_signal(value=value)


def test_signal_is_immutable() -> None:
    signal = make_signal()

    with pytest.raises(ValidationError):
        signal.value = 0.1


def test_advice_with_direction_and_conviction_is_actionable() -> None:
    advice = Advice(
        symbol="BTC/USD",
        timestamp=NOW,
        direction=Direction.BUY,
        conviction=0.7,
        rationale="EMA cross confirmed by positive news flow",
        signals=(make_signal(),),
    )

    assert advice.is_actionable


@pytest.mark.parametrize(
    ("direction", "conviction"),
    [(Direction.HOLD, 0.9), (Direction.BUY, 0.0)],
)
def test_advice_is_not_actionable_when_hold_or_zero_conviction(
    direction: Direction, conviction: float
) -> None:
    advice = Advice(
        symbol="BTC/USD",
        timestamp=NOW,
        direction=direction,
        conviction=conviction,
        rationale="insufficient evidence",
    )

    assert not advice.is_actionable
