"""Shared constrained types for the domain layer."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, Field


def to_utc(value: datetime) -> datetime:
    """Reject naive datetimes outright; normalise aware ones to UTC.

    Silently assuming a timezone is how look-ahead bias and off-by-hours
    backtest bugs get in, so a missing tzinfo is an error, not a default.
    """
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def normalise_symbol(value: str) -> str:
    symbol = value.strip().upper()
    if not symbol:
        raise ValueError("symbol must not be blank")
    return symbol


UtcDatetime = Annotated[datetime, AfterValidator(to_utc)]
Symbol = Annotated[str, AfterValidator(normalise_symbol)]

Price = Annotated[Decimal, Field(ge=Decimal(0))]
Quantity = Annotated[Decimal, Field(ge=Decimal(0))]

#: 0.0 -> 1.0, used for conviction and confidence.
UnitInterval = Annotated[float, Field(ge=0.0, le=1.0)]
#: -1.0 -> 1.0, used for directional signal and sentiment strength.
SignedUnit = Annotated[float, Field(ge=-1.0, le=1.0)]
