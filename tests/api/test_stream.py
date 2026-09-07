"""The merged feed. Ordering across three sources is the only interesting part."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from moneymaker.api.stream import build_stream
from moneymaker.domain import (
    Advice,
    ContentSource,
    Direction,
    NewsEvent,
    SocialPost,
)

NOW = datetime(2024, 1, 1, 12, tzinfo=UTC)


def make_news(*, offset: int = 0, symbols: frozenset[str] = frozenset({"BTC/USD"})) -> NewsEvent:
    published = NOW - timedelta(minutes=offset)
    return NewsEvent(
        id=f"news-{offset}",
        source=ContentSource.RSS,
        feed="coindesk",
        url="https://example.com/a",
        title="Bitcoin rallies",
        body="A long article body. " * 40,
        published_at=published,
        fetched_at=NOW,
        symbols=symbols,
    )


def make_post(*, offset: int = 0) -> SocialPost:
    return SocialPost(
        id=f"post-{offset}",
        source=ContentSource.REDDIT,
        author="someone",
        url="https://example.com/p",
        body="ETH looks strong here",
        created_at=NOW - timedelta(minutes=offset),
        fetched_at=NOW,
        score=10,
        author_weight=0.5,
        symbols=frozenset({"ETH/USD"}),
    )


def make_advice(*, offset: int = 0) -> Advice:
    return Advice(
        symbol="BTC/USD",
        timestamp=NOW - timedelta(minutes=offset),
        direction=Direction.BUY,
        conviction=0.6,
        rationale="trend and momentum agree",
        signals=(),
    )


def test_sources_interleave_newest_first() -> None:
    stream = build_stream(
        news=(make_news(offset=10),),
        posts=(make_post(offset=5),),
        advice=(make_advice(offset=1),),
    )

    assert [event.kind for event in stream] == ["advice", "social", "news"]


def test_events_carry_readable_asset_names() -> None:
    stream = build_stream(advice=(make_advice(),))

    assert stream[0].names == ("Bitcoin",)
    assert stream[0].title == "BUY Bitcoin"


def test_long_bodies_are_truncated() -> None:
    summary = build_stream(news=(make_news(),))[0].summary

    assert len(summary) <= 280
    assert summary.endswith("\u2026")


def test_symbol_filter_drops_unrelated_events() -> None:
    stream = build_stream(
        news=(make_news(),),
        posts=(make_post(),),
        symbols=frozenset({"ETH/USD"}),
    )

    assert [event.kind for event in stream] == ["social"]


def test_untagged_news_survives_when_unfiltered() -> None:
    """Market-wide headlines carry no symbol but still move everything."""
    stream = build_stream(news=(make_news(symbols=frozenset()),))

    assert len(stream) == 1
    assert stream[0].symbols == ()


def test_limit_keeps_the_newest() -> None:
    stream = build_stream(
        news=tuple(make_news(offset=n) for n in range(10)),
        limit=3,
    )

    assert len(stream) == 3
    assert stream[0].timestamp == NOW


def test_ids_are_namespaced_per_source() -> None:
    stream = build_stream(news=(make_news(),), posts=(make_post(),), advice=(make_advice(),))

    prefixes = {event.id.split(":", 1)[0] for event in stream}
    assert prefixes == {"news", "social", "advice"}


def test_advice_events_expose_direction_and_conviction() -> None:
    event = build_stream(advice=(make_advice(),))[0]

    assert event.direction is Direction.BUY
    assert event.conviction == 0.6


def test_empty_input_is_an_empty_stream() -> None:
    assert build_stream() == []
