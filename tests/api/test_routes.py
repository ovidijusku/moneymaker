from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest_asyncio
from asgi_lifespan import LifespanManager

from moneymaker.api import create_app
from moneymaker.domain import Advice, Bar, Direction, NewsEvent, Signal, SignalSource
from moneymaker.persistence import store_advice, store_bars, store_news
from tests.test_config import make_settings

NOW = datetime.now(tz=UTC)


def make_advice(symbol: str = "BTC/USD", minutes: int = 0) -> Advice:
    stamp = NOW - timedelta(minutes=minutes)
    return Advice(
        symbol=symbol,
        timestamp=stamp,
        direction=Direction.BUY,
        conviction=0.5,
        rationale="trend and news agree",
        signals=(
            Signal(
                symbol=symbol,
                timestamp=stamp,
                source=SignalSource.TECHNICAL,
                name="trend_ema",
                value=0.4,
                weight=0.6,
            ),
        ),
    )


def make_bar(symbol: str = "BTC/USD", minutes: int = 0) -> Bar:
    return Bar(
        symbol=symbol,
        timestamp=NOW - timedelta(minutes=minutes),
        open=Decimal("100.5"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("2"),
    )


def make_news(event_id: str = "n1", symbol: str = "BTC/USD") -> NewsEvent:
    return NewsEvent(
        id=event_id,
        feed="coindesk",
        url=f"https://example.com/{event_id}",
        title="Bitcoin rallies",
        published_at=NOW,
        fetched_at=NOW,
        symbols=frozenset({symbol}),
    )


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings(database_url="sqlite+aiosqlite:///:memory:"))
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as active:
            active.app = app  # type: ignore[attr-defined]
            yield active


async def seed(client: httpx.AsyncClient) -> None:
    factory = client.app.state.session_factory  # type: ignore[attr-defined]
    async with factory() as session:
        await store_advice(session, [make_advice(minutes=5), make_advice(minutes=1)])
        await store_advice(session, [make_advice("ETH/USD", minutes=2)])
        await store_bars(session, [make_bar(minutes=2), make_bar(minutes=1)])
        await store_news(session, [make_news(), make_news("n2", "ETH/USD")])
        await session.commit()


async def test_health_reports_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_config_never_exposes_credentials(client: httpx.AsyncClient) -> None:
    body = await client.get("/api/config")

    assert body.json()["trading_mode"] == "advisory"
    assert "alpaca" not in body.text.lower()


async def test_advice_returns_the_journal(client: httpx.AsyncClient) -> None:
    await seed(client)

    body = (await client.get("/api/advice")).json()

    assert len(body) == 3
    assert body[0]["signals"][0]["name"] == "trend_ema"


async def test_advice_filters_by_symbol(client: httpx.AsyncClient) -> None:
    await seed(client)

    body = (await client.get("/api/advice", params={"symbol": "ETH/USD"})).json()

    assert [item["symbol"] for item in body] == ["ETH/USD"]


async def test_latest_advice_returns_one_row_per_symbol(client: httpx.AsyncClient) -> None:
    await seed(client)

    body = (await client.get("/api/advice/latest")).json()

    assert [item["symbol"] for item in body] == ["BTC/USD", "ETH/USD"]


async def test_latest_advice_is_empty_before_the_worker_runs(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/advice/latest")).json() == []


async def test_bars_preserve_decimal_precision(client: httpx.AsyncClient) -> None:
    await seed(client)

    body = (await client.get("/api/bars", params={"symbol": "BTC/USD"})).json()

    assert len(body) == 2
    assert body[0]["open"] == "100.5"


async def test_bars_require_a_symbol(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/bars")).status_code == 422


async def test_news_filters_by_symbol_tag(client: httpx.AsyncClient) -> None:
    await seed(client)

    body = (await client.get("/api/news", params={"symbol": "ETH/USD"})).json()

    assert [item["id"] for item in body] == ["n2"]


async def test_lookback_window_is_bounded(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/advice", params={"hours": 10_000})).status_code == 422
    assert (await client.get("/api/advice", params={"hours": 0})).status_code == 422
