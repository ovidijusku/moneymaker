"""Sizing and stops. These numbers decide how much of the account a bad call costs."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from moneymaker.analysis.indicators import IndicatorSnapshot
from moneymaker.domain import Advice, Direction, Portfolio, Position
from moneymaker.strategy.plan import PlanAction, RiskConfig, build_plan

NOW = datetime(2024, 1, 1, 12, tzinfo=UTC)


def make_snapshot(*, close: float = 10.0, atr: float = 2.0) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        symbol="BTC/USD",
        timestamp=NOW,
        close=close,
        ema_fast=close,
        ema_slow=close,
        rsi=55.0,
        atr=atr,
        volume_ratio=1.0,
    )


def make_advice(
    direction: Direction = Direction.BUY,
    conviction: float = 0.8,
) -> Advice:
    return Advice(
        symbol="BTC/USD",
        timestamp=NOW,
        direction=direction,
        conviction=conviction,
        rationale="test",
        signals=(),
    )


def make_portfolio(
    *,
    equity: str = "100000",
    cash: str = "100000",
    positions: tuple[Position, ...] = (),
) -> Portfolio:
    return Portfolio(
        timestamp=NOW,
        equity=Decimal(equity),
        cash=Decimal(cash),
        positions=positions,
    )


def make_position(*, quantity: str = "10", value: str = "1000") -> Position:
    return Position(
        symbol="BTC/USD",
        quantity=Decimal(quantity),
        average_entry=Decimal("95"),
        market_value=Decimal(value),
        unrealised_pnl=Decimal("50"),
    )


def test_size_comes_from_the_stop_distance() -> None:
    # 0.5% of 100k = 500 risked; stop sits 2 x ATR(2) = 4 below, so 125 units.
    plan = build_plan(
        advice=make_advice(),
        snapshot=make_snapshot(),
        portfolio=make_portfolio(),
    )

    assert plan.action is PlanAction.BUY
    assert plan.quantity == Decimal("125")
    assert plan.stop == Decimal("6")
    assert plan.risk_amount == Decimal("500.00")


def test_a_wider_stop_buys_less() -> None:
    """The whole point of risk-based sizing: volatility shrinks the position."""
    calm = build_plan(
        advice=make_advice(),
        snapshot=make_snapshot(atr=1.0),
        portfolio=make_portfolio(),
    )
    wild = build_plan(
        advice=make_advice(),
        snapshot=make_snapshot(atr=3.0),
        portfolio=make_portfolio(),
    )

    assert wild.quantity < calm.quantity
    # Rounding is always downward, so the budget is approached but never exceeded.
    assert wild.risk_amount <= calm.risk_amount == Decimal("500.00")
    assert wild.risk_amount > Decimal("499")


def test_target_sits_beyond_the_stop() -> None:
    plan = build_plan(
        advice=make_advice(),
        snapshot=make_snapshot(),
        portfolio=make_portfolio(),
    )

    assert plan.target > plan.price > plan.stop
    assert plan.reward_to_risk == pytest.approx(1.5)


def test_position_cap_limits_a_large_size() -> None:
    # A tight stop would otherwise buy far more than 10% of equity.
    plan = build_plan(
        advice=make_advice(),
        snapshot=make_snapshot(atr=0.05),
        portfolio=make_portfolio(),
    )

    assert plan.notional <= Decimal("10000")
    assert any("position cap" in note for note in plan.notes)


def test_cash_caps_the_size() -> None:
    plan = build_plan(
        advice=make_advice(),
        snapshot=make_snapshot(atr=0.05),
        portfolio=make_portfolio(equity="100000", cash="500"),
    )

    assert plan.notional <= Decimal("500")
    assert any("available cash" in note for note in plan.notes)


def test_gross_exposure_cap_applies() -> None:
    held = Position(
        symbol="ETH/USD",
        quantity=Decimal("1"),
        average_entry=Decimal("59000"),
        market_value=Decimal("59000"),
        unrealised_pnl=Decimal("0"),
    )
    plan = build_plan(
        advice=make_advice(),
        snapshot=make_snapshot(atr=0.05),
        portfolio=make_portfolio(positions=(held,)),
    )

    assert any("gross exposure" in note for note in plan.notes)
    assert plan.notional <= Decimal("1000")


def test_existing_holding_reduces_the_room_to_add() -> None:
    plan = build_plan(
        advice=make_advice(),
        snapshot=make_snapshot(atr=0.05),
        portfolio=make_portfolio(positions=(make_position(value="9500"),)),
    )

    assert plan.action is PlanAction.ADD
    assert plan.held_quantity == Decimal("10")
    assert plan.notional <= Decimal("500")


def test_a_dust_size_is_not_worth_suggesting() -> None:
    plan = build_plan(
        advice=make_advice(),
        snapshot=make_snapshot(),
        portfolio=make_portfolio(equity="100", cash="5"),
    )

    assert plan.action is PlanAction.STAND_ASIDE
    assert plan.quantity == Decimal(0)
    assert any("minimum notional" in note for note in plan.notes)


def test_sell_without_a_position_stands_aside_rather_than_shorting() -> None:
    """Alpaca lists zero shortable crypto pairs, so a bearish read has no trade."""
    plan = build_plan(
        advice=make_advice(Direction.SELL),
        snapshot=make_snapshot(),
        portfolio=make_portfolio(),
    )

    assert plan.action is PlanAction.STAND_ASIDE
    assert plan.quantity == Decimal(0)
    assert plan.shortable is False
    assert any("spot-only" in note for note in plan.notes)


def test_strong_sell_exits_the_whole_position() -> None:
    plan = build_plan(
        advice=make_advice(Direction.SELL),
        snapshot=make_snapshot(),
        portfolio=make_portfolio(positions=(make_position(),)),
    )

    assert plan.action is PlanAction.EXIT
    assert plan.quantity == Decimal("10")


def test_weak_sell_only_trims() -> None:
    plan = build_plan(
        advice=make_advice(Direction.SELL, conviction=0.05),
        snapshot=make_snapshot(),
        portfolio=make_portfolio(positions=(make_position(),)),
    )

    assert plan.action is PlanAction.REDUCE
    assert plan.quantity == Decimal("5")


def test_weak_buy_without_a_position_does_nothing() -> None:
    plan = build_plan(
        advice=make_advice(conviction=0.01),
        snapshot=make_snapshot(),
        portfolio=make_portfolio(),
    )

    assert plan.action is PlanAction.STAND_ASIDE
    assert plan.quantity == Decimal(0)


def test_hold_keeps_the_stop_visible_for_an_open_position() -> None:
    plan = build_plan(
        advice=make_advice(Direction.HOLD),
        snapshot=make_snapshot(),
        portfolio=make_portfolio(positions=(make_position(),)),
    )

    assert plan.action is PlanAction.HOLD
    assert plan.stop == Decimal("6")
    assert any("already hold" in note for note in plan.notes)


def test_zero_atr_still_produces_a_usable_stop() -> None:
    """A flat series must not collapse the stop onto the entry and divide by zero."""
    plan = build_plan(
        advice=make_advice(),
        snapshot=make_snapshot(atr=0.0),
        portfolio=make_portfolio(),
    )

    assert plan.stop < plan.price
    assert plan.quantity > 0


def test_target_must_be_further_out_than_the_stop() -> None:
    with pytest.raises(ValueError, match="target_atr_multiple"):
        RiskConfig(stop_atr_multiple=3.0, target_atr_multiple=2.0)


def test_custom_risk_budget_scales_the_size() -> None:
    plan = build_plan(
        advice=make_advice(),
        snapshot=make_snapshot(),
        portfolio=make_portfolio(),
        config=RiskConfig(risk_per_trade=0.01),
    )

    assert plan.quantity == Decimal("250")
