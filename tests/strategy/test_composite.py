from __future__ import annotations

from datetime import UTC, datetime

import pytest

from moneymaker.domain import Advice, Direction, Signal, SignalSource
from moneymaker.strategy.composite import CompositeConfig, blend, build_advice

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _signal(
    value: float,
    *,
    source: SignalSource = SignalSource.TECHNICAL,
    weight: float = 1.0,
    name: str = "trend_ema",
) -> Signal:
    return Signal(
        symbol="BTC/USD",
        timestamp=NOW,
        source=source,
        name=name,
        value=value,
        weight=weight,
    )


def _advice(
    signals: list[Signal],
    *,
    volatility: float | None = None,
    config: CompositeConfig | None = None,
) -> Advice:
    return build_advice(
        symbol="BTC/USD",
        timestamp=NOW,
        signals=signals,
        volatility=volatility,
        config=config,
    )


def test_no_signals_blend_to_zero() -> None:
    assert blend([], CompositeConfig()) == 0.0


def test_zero_weight_signals_blend_to_zero() -> None:
    assert blend([_signal(1.0, weight=0.0)], CompositeConfig()) == 0.0


def test_technical_outweighs_social_by_default() -> None:
    score = blend(
        [
            _signal(1.0, source=SignalSource.TECHNICAL),
            _signal(-1.0, source=SignalSource.SOCIAL),
        ],
        CompositeConfig(),
    )

    assert score > 0


def test_source_weights_are_configurable() -> None:
    config = CompositeConfig(technical_weight=0.0, social_weight=1.0)

    score = blend(
        [
            _signal(1.0, source=SignalSource.TECHNICAL),
            _signal(-1.0, source=SignalSource.SOCIAL),
        ],
        config,
    )

    assert score == pytest.approx(-1.0)


def test_strong_positive_score_advises_buy() -> None:
    advice = _advice([_signal(1.0)])

    assert advice.direction is Direction.BUY
    assert advice.is_actionable


def test_strong_negative_score_advises_sell() -> None:
    advice = _advice([_signal(-1.0)])

    assert advice.direction is Direction.SELL


def test_weak_score_advises_hold_with_zero_conviction() -> None:
    advice = _advice([_signal(0.05)])

    assert advice.direction is Direction.HOLD
    assert advice.conviction == 0.0
    assert not advice.is_actionable


def test_score_exactly_at_the_threshold_is_actionable() -> None:
    config = CompositeConfig(action_threshold=0.2)

    advice = _advice([_signal(0.2)], config=config)

    assert advice.direction is Direction.BUY


def test_calm_volatility_leaves_conviction_untouched() -> None:
    advice = _advice([_signal(1.0)], volatility=0.01)

    assert advice.conviction == pytest.approx(1.0)


def test_excess_volatility_damps_conviction() -> None:
    config = CompositeConfig(volatility_ceiling=0.05)

    calm = _advice([_signal(1.0)], volatility=0.05, config=config)
    wild = _advice([_signal(1.0)], volatility=0.5, config=config)

    assert wild.conviction < calm.conviction
    assert wild.conviction == pytest.approx(0.1)


def test_missing_volatility_does_not_damp() -> None:
    assert _advice([_signal(1.0)]).conviction == pytest.approx(1.0)


def test_advice_carries_its_signals_and_a_readable_rationale() -> None:
    signals = [
        _signal(0.9),
        _signal(0.4, source=SignalSource.NEWS, name="sentiment_news"),
    ]

    advice = _advice(signals)

    assert advice.signals == tuple(signals)
    assert "trend_ema=+0.90" in advice.rationale
    assert "sentiment_news=+0.40" in advice.rationale


def test_rationale_is_readable_with_no_signals() -> None:
    assert "no signals" in _advice([]).rationale


def test_all_zero_source_weights_are_rejected() -> None:
    with pytest.raises(ValueError, match="source weight"):
        CompositeConfig(technical_weight=0.0, news_weight=0.0, social_weight=0.0)
