"""The account snapshot job. A broker outage must degrade sizing, not stop the worker."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio

from moneymaker.persistence import (
    create_engine,
    create_schema,
    create_session_factory,
    latest_portfolio,
)
from moneymaker.pipeline.jobs import SessionFactory
from moneymaker.pipeline.portfolio import poll_portfolio

NOW = datetime(2024, 1, 1, tzinfo=UTC)


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[SessionFactory]:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await create_schema(engine)
    yield create_session_factory(engine)
    await engine.dispose()


class FakeAccount:
    equity = "100000"
    cash = "40000"


class FakeRawPosition:
    symbol = "ETHUSD"
    qty = "2"
    avg_entry_price = "3000"
    market_value = "6000"
    unrealized_pl = "120"


class FakeTradingClient:
    def get_account(self) -> FakeAccount:
        return FakeAccount()

    def get_all_positions(self) -> list[FakeRawPosition]:
        return [FakeRawPosition()]


class BrokenTradingClient:
    def get_account(self) -> FakeAccount:
        raise RuntimeError("broker is down")

    def get_all_positions(self) -> list[FakeRawPosition]:
        return []


async def test_snapshot_is_persisted(factory: SessionFactory) -> None:
    portfolio = await poll_portfolio(factory, FakeTradingClient(), now=NOW)

    assert portfolio is not None
    async with factory() as session:
        stored = await latest_portfolio(session)

    assert stored is not None
    assert stored.equity == Decimal("100000")
    assert stored.position_for("ETH/USD") is not None


async def test_broker_failure_is_contained(factory: SessionFactory) -> None:
    assert await poll_portfolio(factory, BrokenTradingClient(), now=NOW) is None

    async with factory() as session:
        assert await latest_portfolio(session) is None


async def test_newest_snapshot_wins(factory: SessionFactory) -> None:
    await poll_portfolio(factory, FakeTradingClient(), now=NOW)
    later = NOW.replace(hour=6)
    await poll_portfolio(factory, FakeTradingClient(), now=later)

    async with factory() as session:
        stored = await latest_portfolio(session)

    assert stored is not None
    assert stored.timestamp == later
