"""Turn advice into a concrete plan: how much, and where to get out.

The stop is chosen first and the size falls out of it. Sizing off conviction
alone is how accounts die -- a 5% stop and a 0.5% stop are not the same bet at
the same notional. Distance to the stop is measured in ATR so a quiet market and
a violent one get different room.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from moneymaker.analysis.indicators import IndicatorSnapshot
from moneymaker.domain import Advice, Direction, Portfolio
from moneymaker.domain.types import Price, Symbol, UnitInterval, UtcDatetime

#: Even a dead-flat series must not produce a zero-width stop.
_MIN_STOP_FRACTION = Decimal("0.005")


class PlanAction(StrEnum):
    """What the user can actually do, given a spot-only venue."""

    BUY = "buy"
    ADD = "add"
    REDUCE = "reduce"
    EXIT = "exit"
    HOLD = "hold"
    STAND_ASIDE = "stand_aside"


class RiskConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Fraction of equity lost if the stop is hit. The one number that matters.
    risk_per_trade: float = Field(default=0.005, gt=0.0, le=0.05)
    #: Ceiling on a single position's notional, as a fraction of equity.
    max_position_pct: float = Field(default=0.10, gt=0.0, le=1.0)
    max_gross_exposure_pct: float = Field(default=0.60, gt=0.0, le=1.0)
    stop_atr_multiple: float = Field(default=2.0, gt=0.0)
    target_atr_multiple: float = Field(default=3.0, gt=0.0)
    #: Below this, fees and spread eat the edge.
    min_notional: Decimal = Decimal(20)
    min_conviction: UnitInterval = 0.15

    @model_validator(mode="after")
    def check_target_beyond_stop(self) -> RiskConfig:
        if self.target_atr_multiple <= self.stop_atr_multiple:
            raise ValueError("target_atr_multiple must exceed stop_atr_multiple")
        return self


class TradePlan(BaseModel):
    """A sized, stopped suggestion. Advisory: nothing here reaches a broker."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: Symbol
    timestamp: UtcDatetime
    action: PlanAction
    direction: Direction
    conviction: UnitInterval

    price: Price
    stop: Price
    target: Price
    quantity: Decimal = Decimal(0)
    notional: Decimal = Decimal(0)
    risk_amount: Decimal = Decimal(0)

    held_quantity: Decimal = Decimal(0)
    held_value: Decimal = Decimal(0)

    #: Why the size is what it is, including whatever capped it.
    notes: tuple[str, ...] = ()
    #: Always False on Alpaca crypto. Explicit so the UI never implies otherwise.
    shortable: bool = False

    @property
    def reward_to_risk(self) -> float:
        risk = abs(self.price - self.stop)
        return 0.0 if risk == 0 else float(abs(self.target - self.price) / risk)


def _round_down(value: Decimal, places: int = 8) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_DOWN)


def _stop_distance(price: Decimal, snapshot: IndicatorSnapshot, config: RiskConfig) -> Decimal:
    atr = Decimal(str(snapshot.atr)) * Decimal(str(config.stop_atr_multiple))
    return max(atr, price * _MIN_STOP_FRACTION)


def _buy_quantity(
    *,
    price: Decimal,
    stop_distance: Decimal,
    portfolio: Portfolio,
    held_value: Decimal,
    config: RiskConfig,
) -> tuple[Decimal, list[str]]:
    """Size from the stop, then let the tightest account constraint win."""
    notes: list[str] = []
    quantity = portfolio.equity * Decimal(str(config.risk_per_trade)) / stop_distance

    caps = (
        (
            portfolio.equity * Decimal(str(config.max_position_pct)) - held_value,
            f"position cap {config.max_position_pct:.0%} of equity",
        ),
        (
            portfolio.equity * Decimal(str(config.max_gross_exposure_pct)) - portfolio.exposure,
            f"gross exposure cap {config.max_gross_exposure_pct:.0%} of equity",
        ),
        (portfolio.cash, "available cash"),
    )
    for room, reason in caps:
        limit = max(room, Decimal(0)) / price
        if limit < quantity:
            quantity = limit
            notes.append(f"capped by {reason}")

    return _round_down(max(quantity, Decimal(0))), notes


def _action_for(advice: Advice, held: Decimal, config: RiskConfig) -> PlanAction:
    weak = advice.conviction < config.min_conviction
    if advice.direction is Direction.BUY and not weak:
        return PlanAction.ADD if held > 0 else PlanAction.BUY
    if advice.direction is Direction.SELL and held > 0:
        return PlanAction.REDUCE if weak else PlanAction.EXIT
    return PlanAction.HOLD if held > 0 else PlanAction.STAND_ASIDE


def build_plan(
    *,
    advice: Advice,
    snapshot: IndicatorSnapshot,
    portfolio: Portfolio,
    config: RiskConfig | None = None,
) -> TradePlan:
    settings = config or RiskConfig()
    price = Decimal(str(snapshot.close))
    distance = _stop_distance(price, snapshot, settings)

    position = portfolio.position_for(advice.symbol)
    held = position.quantity if position else Decimal(0)
    held_value = position.market_value if position else Decimal(0)

    action = _action_for(advice, held, settings)
    notes: list[str] = []
    quantity = Decimal(0)

    if action in (PlanAction.BUY, PlanAction.ADD):
        quantity, notes = _buy_quantity(
            price=price,
            stop_distance=distance,
            portfolio=portfolio,
            held_value=held_value,
            config=settings,
        )
        if quantity * price < settings.min_notional:
            quantity = Decimal(0)
            action = PlanAction.HOLD if held > 0 else PlanAction.STAND_ASIDE
            notes.append(f"size fell below the {settings.min_notional} minimum notional")
    elif action is PlanAction.EXIT:
        quantity = held
    elif action is PlanAction.REDUCE:
        quantity = _round_down(held / 2)

    if advice.direction is Direction.SELL and held <= 0:
        notes.append("spot-only venue: a bearish read means stand aside, not short")
    if held > 0 and action is not PlanAction.BUY:
        notes.append("stop applies to the position you already hold")

    reward = Decimal(str(settings.target_atr_multiple / settings.stop_atr_multiple))
    return TradePlan(
        symbol=advice.symbol,
        timestamp=advice.timestamp,
        action=action,
        direction=advice.direction,
        conviction=advice.conviction,
        price=price,
        stop=max(price - distance, Decimal(0)),
        target=price + distance * reward,
        quantity=quantity,
        notional=_round_down(quantity * price, 2),
        risk_amount=_round_down(quantity * distance, 2),
        held_quantity=held,
        held_value=held_value,
        notes=tuple(notes),
    )
