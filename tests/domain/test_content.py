from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from moneymaker.domain import ContentSource, NewsEvent, SentimentScore, SocialPost, content_id

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_content_id_is_stable_for_same_input() -> None:
    assert content_id("a", "b") == content_id("a", "b")


def test_content_id_differs_across_field_boundaries() -> None:
    assert content_id("ab", "c") != content_id("a", "bc")


def test_news_event_defaults_to_rss_and_no_symbols() -> None:
    event = NewsEvent(
        id=content_id("https://example.com/x"),
        feed="coindesk",
        url="https://example.com/x",
        title="Bitcoin moves",
        published_at=NOW,
        fetched_at=NOW,
    )

    assert event.source is ContentSource.RSS
    assert event.symbols == frozenset()


def test_social_post_normalises_symbols() -> None:
    post = SocialPost(
        id="abc",
        source=ContentSource.REDDIT,
        author="someone",
        url="https://reddit.com/r/x/1",
        body="to the moon",
        created_at=NOW,
        fetched_at=NOW,
        author_weight=0.5,
        symbols=frozenset({"btc/usd"}),
    )

    assert post.symbols == frozenset({"BTC/USD"})


def test_social_post_rejects_author_weight_above_one() -> None:
    with pytest.raises(ValidationError):
        SocialPost(
            id="abc",
            source=ContentSource.REDDIT,
            author="someone",
            url="https://reddit.com/r/x/1",
            body="hi",
            created_at=NOW,
            fetched_at=NOW,
            author_weight=1.5,
        )


def test_sentiment_score_rejects_polarity_out_of_range() -> None:
    with pytest.raises(ValidationError):
        SentimentScore(
            content_id="abc",
            model="finbert",
            polarity=-2.0,
            scored_at=NOW,
        )


def test_sentiment_score_accepts_bounds() -> None:
    score = SentimentScore(
        content_id="abc",
        model="finbert",
        polarity=-1.0,
        confidence=1.0,
        scored_at=NOW,
    )

    assert score.polarity == -1.0
