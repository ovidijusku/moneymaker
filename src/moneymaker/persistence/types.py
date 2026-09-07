"""Column types that keep financial precision and timezone awareness intact."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Dialect, String, TypeDecorator


class UtcTimestamp(TypeDecorator[datetime]):
    """Timezone-aware timestamp. SQLite drops tzinfo, so it is reattached on read."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("refusing to persist a naive datetime")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class ExactDecimal(TypeDecorator[Decimal]):
    """Decimal stored as text.

    SQLite has no native decimal and would silently round-trip prices through
    a float, so the exact string form is stored instead.
    """

    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return str(Decimal(value))

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        return Decimal(value)
