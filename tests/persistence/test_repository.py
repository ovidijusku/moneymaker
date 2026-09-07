from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from moneymaker.domain import (
    Advice,
    Bar,
    ContentSource,
    Direction,
    NewsEvent,
    SentimentScore,
    Signal,
    SignalSource,
    SocialPost,
    content_id,
)
from moneymaker.persistence import (
    create_engine,
    create_schema,
    create_session_factory,
    latest_bar_timestamp,
    load_advice,
    load_bars,
    load_news,
    load_posts,
    load_sentiment,
    store_advice,
    store_bars,
    store_news,
    store_posts,
    store_sentiment,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await create_schema(engine)
    factory = create_session_factory(engine)
    async with factory() as active:
        yield active
    await engine.dispose()


def make_bar(minute: int = 0, **overrides: object) -> Bar:
    defaults: dict[str, object] = {
        "symbol": "BTC/USD",
        "timestamp": NOW + timedelta(minutes=minute),
        "open": Decimal("100.12345678"),
        "high": Decimal("110"),
        "low": Decimal("90"),
        "close": Decimal("105"),
        "volume": Decimal("3.5"),
    }
    return Bar(**{**defaults, **overrides})  # type: ignore[arg-type]


async def test_store_bars_round_trips_without_precision_loss(
    session: AsyncSession,
) -> None:
    await store_bars(session, [make_bar()])

    stored = await load_bars(session, "BTC/USD")

    assert stored == (make_bar(),)
    assert stored[0].open == Decimal("100.12345678")


async def test_store_bars_is_idempotent_on_replay(session: AsyncSession) -> None:
    await store_bars(session, [make_bar(), make_bar(1)])
    inserted = await store_bars(session, [make_bar(), make_bar(1), make_bar(2)])

    assert inserted == 1
    assert len(await load_bars(session, "BTC/USD")) == 3


async def test_store_bars_ignores_empty_input(session: AsyncSession) -> None:
    assert await store_bars(session, []) == 0


async def test_store_bars_survives_a_full_universe_backfill(session: AsyncSession) -> None:
    """One statement per write blew past Postgres' 32767 bind-parameter cap once
    the universe grew to 32 symbols, so writes have to be chunked."""
    bars = [make_bar(minute) for minute in range(6000)]

    assert await store_bars(session, bars) == 6000
    assert len(await load_bars(session, "BTC/USD")) == 6000


async def test_load_bars_filters_by_window_and_orders_ascending(
    session: AsyncSession,
) -> None:
    await store_bars(session, [make_bar(2), make_bar(0), make_bar(1)])

    stored = await load_bars(
        session,
        "BTC/USD",
        since=NOW + timedelta(minutes=1),
        until=NOW + timedelta(minutes=2),
    )

    assert [bar.timestamp for bar in stored] == [NOW + timedelta(minutes=1)]


async def test_load_bars_returns_timezone_aware_timestamps(
    session: AsyncSession,
) -> None:
    await store_bars(session, [make_bar()])

    stored = await load_bars(session, "BTC/USD")

    assert stored[0].timestamp.tzinfo is not None
    assert stored[0].timestamp == NOW


async def test_latest_bar_timestamp_tracks_backfill_resume_point(
    session: AsyncSession,
) -> None:
    assert await latest_bar_timestamp(session, "BTC/USD") is None

    await store_bars(session, [make_bar(0), make_bar(5), make_bar(2)])

    assert await latest_bar_timestamp(session, "BTC/USD") == NOW + timedelta(minutes=5)


async def test_latest_bar_timestamp_is_scoped_per_symbol(session: AsyncSession) -> None:
    await store_bars(session, [make_bar(symbol="ETH/USD")])

    assert await latest_bar_timestamp(session, "BTC/USD") is None


async def test_store_news_deduplicates_by_content_id(session: AsyncSession) -> None:
    event = NewsEvent(
        id=content_id("https://example.com/a"),
        feed="coindesk",
        url="https://example.com/a",
        title="Bitcoin rallies",
        published_at=NOW,
        fetched_at=NOW,
        symbols=frozenset({"BTC/USD"}),
    )

    assert await store_news(session, [event]) == 1
    assert await store_news(session, [event]) == 0


async def test_store_posts_persists_author_weight(session: AsyncSession) -> None:
    post = SocialPost(
        id="post-1",
        source=ContentSource.REDDIT,
        author="whale",
        url="https://reddit.com/r/x/1",
        body="accumulating",
        created_at=NOW,
        fetched_at=NOW,
        score=42,
        author_weight=0.8,
        symbols=frozenset({"BTC/USD"}),
    )

    assert await store_posts(session, [post]) == 1
    assert await store_posts(session, [post]) == 0


async def test_store_sentiment_is_keyed_by_content_and_model(
    session: AsyncSession,
) -> None:
    def score(model: str) -> SentimentScore:
        return SentimentScore(
            content_id="abc", model=model, polarity=0.4, confidence=0.9, scored_at=NOW
        )

    assert await store_sentiment(session, [score("finbert")]) == 1
    assert await store_sentiment(session, [score("finbert")]) == 0
    assert await store_sentiment(session, [score("roberta")]) == 1


async def test_unsupported_dialect_is_rejected() -> None:
    from moneymaker.persistence.repository import BAR_TABLE, _insert_ignore

    with pytest.raises(NotImplementedError, match="mysql"):
        _insert_ignore("mysql", BAR_TABLE, [{"symbol": "BTC/USD"}])


def make_news(event_id: str = "n1", minute: int = 0) -> NewsEvent:
    return NewsEvent(
        id=event_id,
        feed="coindesk",
        url=f"https://example.com/{event_id}",
        title="Bitcoin rallies",
        published_at=NOW + timedelta(minutes=minute),
        fetched_at=NOW,
        symbols=frozenset({"BTC/USD"}),
    )


def make_post(post_id: str = "p1", minute: int = 0) -> SocialPost:
    return SocialPost(
        id=post_id,
        source=ContentSource.REDDIT,
        author="whale",
        url=f"https://reddit.com/r/x/{post_id}",
        body="accumulating",
        created_at=NOW + timedelta(minutes=minute),
        fetched_at=NOW,
        author_weight=0.8,
        symbols=frozenset({"BTC/USD"}),
    )


def make_advice(minute: int = 0, symbol: str = "BTC/USD") -> Advice:
    return Advice(
        symbol=symbol,
        timestamp=NOW + timedelta(minutes=minute),
        direction=Direction.BUY,
        conviction=0.42,
        rationale="trend and news agree",
        signals=(
            Signal(
                symbol=symbol,
                timestamp=NOW + timedelta(minutes=minute),
                source=SignalSource.TECHNICAL,
                name="trend_ema",
                value=0.5,
                weight=0.6,
                evidence=("ema_spread=0.01",),
            ),
        ),
    )


async def test_load_news_filters_by_publication_window(session: AsyncSession) -> None:
    await store_news(session, [make_news("old", -60), make_news("new", 0)])

    recent = await load_news(session, since=NOW - timedelta(minutes=10))

    assert [event.id for event in recent] == ["new"]
    assert recent[0].symbols == frozenset({"BTC/USD"})


async def test_load_news_without_a_window_returns_everything(session: AsyncSession) -> None:
    await store_news(session, [make_news("a", -60), make_news("b", 0)])

    assert len(await load_news(session)) == 2


async def test_load_posts_preserves_author_weight(session: AsyncSession) -> None:
    await store_posts(session, [make_post()])

    posts = await load_posts(session, since=NOW - timedelta(minutes=1))

    assert posts[0].author_weight == 0.8
    assert posts[0].source is ContentSource.REDDIT


async def test_load_sentiment_returns_a_cache_keyed_by_content_id(
    session: AsyncSession,
) -> None:
    await store_sentiment(
        session,
        [
            SentimentScore(
                content_id="abc", model="lex", polarity=0.4, confidence=0.9, scored_at=NOW
            )
        ],
    )

    cache = await load_sentiment(session, ["abc", "missing"], model="lex")

    assert set(cache) == {"abc"}
    assert cache["abc"].polarity == 0.4


async def test_load_sentiment_ignores_other_models(session: AsyncSession) -> None:
    await store_sentiment(
        session,
        [
            SentimentScore(
                content_id="abc", model="lex", polarity=0.4, confidence=0.9, scored_at=NOW
            )
        ],
    )

    assert await load_sentiment(session, ["abc"], model="finbert") == {}


async def test_load_sentiment_short_circuits_on_empty_input(session: AsyncSession) -> None:
    assert await load_sentiment(session, [], model="lex") == {}


async def test_store_advice_round_trips_its_signals(session: AsyncSession) -> None:
    await store_advice(session, [make_advice()])

    stored = await load_advice(session)

    assert stored == (make_advice(),)
    assert stored[0].signals[0].evidence == ("ema_spread=0.01",)


async def test_store_advice_keeps_the_first_opinion_for_a_bar(session: AsyncSession) -> None:
    await store_advice(session, [make_advice()])

    assert await store_advice(session, [make_advice()]) == 0
    assert len(await load_advice(session)) == 1


async def test_store_advice_ignores_empty_input(session: AsyncSession) -> None:
    assert await store_advice(session, []) == 0


async def test_load_advice_filters_by_symbol_and_window(session: AsyncSession) -> None:
    await store_advice(
        session,
        [make_advice(0), make_advice(5), make_advice(0, symbol="ETH/USD")],
    )

    stored = await load_advice(session, symbol="BTC/USD", since=NOW + timedelta(minutes=1))

    assert [item.timestamp for item in stored] == [NOW + timedelta(minutes=5)]
