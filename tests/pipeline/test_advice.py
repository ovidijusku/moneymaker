from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio

from moneymaker.analysis.indicators import IndicatorConfig
from moneymaker.analysis.sentiment import MODEL_NAME
from moneymaker.domain import Bar, ContentSource, NewsEvent, SocialPost
from moneymaker.persistence import (
    create_engine,
    create_schema,
    create_session_factory,
    load_advice,
    load_sentiment,
    store_bars,
    store_news,
    store_posts,
)
from moneymaker.pipeline.advice import poll_advice
from moneymaker.pipeline.jobs import SessionFactory
from moneymaker.strategy.evaluate import StrategyConfig

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
CONFIG = StrategyConfig(
    indicators=IndicatorConfig(
        ema_fast=3,
        ema_slow=5,
        rsi_period=3,
        atr_period=3,
        volume_lookback=3,
    )
)


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[SessionFactory]:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await create_schema(engine)
    yield create_session_factory(engine)
    await engine.dispose()


def _bars(count: int = 20) -> list[Bar]:
    return [
        Bar(
            symbol="BTC/USD",
            timestamp=NOW - timedelta(minutes=count - index),
            open=Decimal(100 + index),
            high=Decimal(101 + index),
            low=Decimal(99 + index),
            close=Decimal(100 + index),
            volume=Decimal(10),
        )
        for index in range(count)
    ]


def _news(event_id: str = "n1", title: str = "Bitcoin rally surges") -> NewsEvent:
    return NewsEvent(
        id=event_id,
        feed="https://feed.example",
        url=f"https://feed.example/{event_id}",
        title=title,
        published_at=NOW - timedelta(minutes=5),
        fetched_at=NOW,
        symbols=frozenset({"BTC/USD"}),
    )


def _post(post_id: str = "p1") -> SocialPost:
    return SocialPost(
        id=post_id,
        source=ContentSource.REDDIT,
        author="whale",
        url=f"https://reddit.example/{post_id}",
        body="massive breakout incoming",
        created_at=NOW - timedelta(minutes=5),
        fetched_at=NOW,
        symbols=frozenset({"BTC/USD"}),
    )


async def test_writes_one_advice_row_per_symbol(factory: SessionFactory) -> None:
    async with factory() as session:
        await store_bars(session, _bars())
        await session.commit()

    stored = await poll_advice(factory, symbols=["BTC/USD"], config=CONFIG, now=NOW)

    assert stored == 1
    async with factory() as session:
        assert len(await load_advice(session, symbol="BTC/USD")) == 1


async def test_skips_symbols_without_enough_history(factory: SessionFactory) -> None:
    async with factory() as session:
        await store_bars(session, _bars(count=3))
        await session.commit()

    assert await poll_advice(factory, symbols=["BTC/USD"], config=CONFIG, now=NOW) == 0


async def test_is_idempotent_for_the_same_bar(factory: SessionFactory) -> None:
    async with factory() as session:
        await store_bars(session, _bars())
        await session.commit()

    first = await poll_advice(factory, symbols=["BTC/USD"], config=CONFIG, now=NOW)
    second = await poll_advice(factory, symbols=["BTC/USD"], config=CONFIG, now=NOW)

    assert (first, second) == (1, 0)
    async with factory() as session:
        assert len(await load_advice(session)) == 1


async def test_scores_and_caches_sentiment_for_new_content(factory: SessionFactory) -> None:
    async with factory() as session:
        await store_bars(session, _bars())
        await store_news(session, [_news()])
        await store_posts(session, [_post()])
        await session.commit()

    await poll_advice(factory, symbols=["BTC/USD"], config=CONFIG, now=NOW)

    async with factory() as session:
        cached = await load_sentiment(session, ["n1", "p1"], model=MODEL_NAME)
    assert set(cached) == {"n1", "p1"}
    assert cached["n1"].polarity > 0


async def test_reuses_cached_sentiment_instead_of_rescoring(factory: SessionFactory) -> None:
    async with factory() as session:
        await store_bars(session, _bars())
        await store_news(session, [_news()])
        await session.commit()

    await poll_advice(factory, symbols=["BTC/USD"], config=CONFIG, now=NOW)
    async with factory() as session:
        first = (await load_sentiment(session, ["n1"], model=MODEL_NAME))["n1"]

    later = NOW + timedelta(hours=1)
    await poll_advice(factory, symbols=["BTC/USD"], config=CONFIG, now=later)
    async with factory() as session:
        second = (await load_sentiment(session, ["n1"], model=MODEL_NAME))["n1"]

    assert second.scored_at == first.scored_at


async def test_news_outside_the_content_window_is_ignored(factory: SessionFactory) -> None:
    stale = _news("old", "Bitcoin rally surges").model_copy(
        update={"published_at": NOW - timedelta(days=7)}
    )
    async with factory() as session:
        await store_bars(session, _bars())
        await store_news(session, [stale])
        await session.commit()

    await poll_advice(factory, symbols=["BTC/USD"], config=CONFIG, now=NOW)

    async with factory() as session:
        assert await load_sentiment(session, ["old"], model=MODEL_NAME) == {}


async def test_advice_round_trips_its_signals(factory: SessionFactory) -> None:
    async with factory() as session:
        await store_bars(session, _bars())
        await session.commit()

    await poll_advice(factory, symbols=["BTC/USD"], config=CONFIG, now=NOW)

    async with factory() as session:
        advice = await load_advice(session)
    assert len(advice[0].signals) == 4
    assert {signal.name for signal in advice[0].signals} == {
        "trend_ema",
        "momentum_rsi",
        "sentiment_news",
        "sentiment_social",
    }


async def test_content_load_failure_is_contained(
    factory: SessionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("query failed")

    monkeypatch.setattr("moneymaker.pipeline.advice.load_news", boom)

    assert await poll_advice(factory, symbols=["BTC/USD"], config=CONFIG, now=NOW) == 0


async def test_unknown_symbol_produces_no_advice(factory: SessionFactory) -> None:
    async with factory() as session:
        await store_bars(session, _bars())
        await session.commit()

    assert await poll_advice(factory, symbols=["ETH/USD"], config=CONFIG, now=NOW) == 0
