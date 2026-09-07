from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest_asyncio
from pydantic import SecretStr

from moneymaker.config import Settings
from moneymaker.domain import Bar
from moneymaker.persistence import (
    create_engine,
    create_schema,
    create_session_factory,
    load_bars,
    store_bars,
)
from moneymaker.pipeline import build_scheduler
from moneymaker.pipeline.jobs import SessionFactory, poll_bars, poll_news, poll_social
from tests.fakes import FakeAlpacaBar, FakeBarsClient, FakeReddit, FakeSubmission

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

FEED_XML = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Bitcoin surges</title>
    <link>https://example.com/a</link>
    <pubDate>Thu, 01 Jan 2026 11:00:00 GMT</pubDate>
  </item>
</channel></rss>
"""


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[SessionFactory]:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await create_schema(engine)
    yield create_session_factory(engine)
    await engine.dispose()


async def test_poll_bars_backfills_lookback_window_when_database_is_empty(
    factory: SessionFactory,
) -> None:
    client = FakeBarsClient([FakeAlpacaBar(timestamp=NOW)])

    stored = await poll_bars(
        factory, client, symbols=["BTC/USD"], lookback=timedelta(hours=2), now=NOW
    )

    assert stored == 1
    assert client.requests[0].start == (NOW - timedelta(hours=2)).replace(tzinfo=None)


async def test_poll_bars_resumes_from_last_stored_bar(factory: SessionFactory) -> None:
    async with factory() as session:
        await store_bars(session, [_bar(NOW)])
        await session.commit()
    client = FakeBarsClient([])

    await poll_bars(
        factory,
        client,
        symbols=["BTC/USD"],
        lookback=timedelta(hours=2),
        now=NOW + timedelta(hours=1),
    )

    assert client.requests[0].start == (NOW + timedelta(seconds=1)).replace(tzinfo=None)


async def test_poll_bars_uses_lookback_when_one_symbol_has_no_history(
    factory: SessionFactory,
) -> None:
    async with factory() as session:
        await store_bars(session, [_bar(NOW)])
        await session.commit()
    client = FakeBarsClient([])

    await poll_bars(
        factory,
        client,
        symbols=["BTC/USD", "ETH/USD"],
        lookback=timedelta(hours=2),
        now=NOW + timedelta(hours=1),
    )

    expected = (NOW + timedelta(hours=1) - timedelta(hours=2)).replace(tzinfo=None)
    assert client.requests[0].start == expected


async def test_poll_bars_is_idempotent_across_runs(factory: SessionFactory) -> None:
    client = FakeBarsClient([FakeAlpacaBar(timestamp=NOW)])

    first = await poll_bars(factory, client, symbols=["BTC/USD"], lookback=timedelta(hours=2))
    second = await poll_bars(factory, client, symbols=["BTC/USD"], lookback=timedelta(hours=2))

    assert (first, second) == (1, 0)
    async with factory() as session:
        assert len(await load_bars(session, "BTC/USD")) == 1


async def test_poll_bars_survives_upstream_failure(factory: SessionFactory) -> None:
    client = FakeBarsClient(error=RuntimeError("alpaca down"))

    assert await poll_bars(factory, client, symbols=["BTC/USD"], lookback=timedelta(hours=2)) == 0


async def test_poll_news_stores_events_from_all_feeds(factory: SessionFactory) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=FEED_XML))

    async with httpx.AsyncClient(transport=transport) as client:
        stored = await poll_news(factory, client, feeds=["https://a.example"], universe=["BTC/USD"])

    assert stored == 1


async def test_poll_news_continues_after_one_feed_fails(
    factory: SessionFactory,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "bad" in str(request.url):
            return httpx.Response(500)
        return httpx.Response(200, content=FEED_XML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        stored = await poll_news(
            factory,
            client,
            feeds=["https://bad.example", "https://good.example"],
            universe=["BTC/USD"],
        )

    assert stored == 1


async def test_poll_social_applies_author_weights(factory: SessionFactory) -> None:
    reddit = FakeReddit([FakeSubmission()])

    stored = await poll_social(
        factory,
        reddit,
        subreddits=["CryptoCurrency"],
        limit=10,
        author_weights={"whalewatcher": 0.9},
        universe=["BTC/USD"],
    )

    assert stored == 1


async def test_poll_social_continues_after_one_subreddit_fails(
    factory: SessionFactory,
) -> None:
    reddit = FakeReddit([FakeSubmission()], failing={"Broken"})

    stored = await poll_social(
        factory,
        reddit,
        subreddits=["Broken", "CryptoCurrency"],
        limit=10,
        author_weights={},
        universe=["BTC/USD"],
    )

    assert stored == 1


def _bar(timestamp: datetime) -> Bar:
    return Bar(
        symbol="BTC/USD",
        timestamp=timestamp,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("1"),
    )


def _job_ids(reddit: object | None) -> set[str]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        alpaca_api_key=SecretStr("k"),
        alpaca_api_secret=SecretStr("s"),
    )
    scheduler = build_scheduler(
        settings,
        None,  # type: ignore[arg-type]
        bars_client=None,
        http_client=None,
        reddit=reddit,
    )
    return {job.id for job in scheduler.get_jobs()}


def test_scheduler_registers_market_and_news_jobs() -> None:
    assert {"bars", "news"} <= _job_ids(None)


def test_scheduler_always_registers_the_advice_job() -> None:
    assert "advice" in _job_ids(None)


def test_scheduler_skips_social_job_without_reddit_client() -> None:
    assert "social" not in _job_ids(None)


def test_scheduler_adds_social_job_when_reddit_available() -> None:
    assert "social" in _job_ids(object())
