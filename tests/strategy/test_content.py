from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from moneymaker.domain import (
    ContentSource,
    NewsEvent,
    SentimentScore,
    Signal,
    SignalSource,
    SocialPost,
)
from moneymaker.strategy.content import (
    ContentConfig,
    ScoredItem,
    aggregate_sentiment,
    news_items,
    social_items,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _item(
    *,
    polarity: float,
    confidence: float = 1.0,
    authority: float = 1.0,
    age: timedelta = timedelta(0),
    label: str = "headline",
) -> ScoredItem:
    return ScoredItem(
        timestamp=NOW - age,
        polarity=polarity,
        confidence=confidence,
        authority=authority,
        label=label,
    )


def _aggregate(items: list[ScoredItem], source: SignalSource = SignalSource.NEWS) -> Signal:
    return aggregate_sentiment(items, symbol="BTC/USD", source=source, now=NOW)


def test_empty_input_yields_a_zero_signal_with_no_weight() -> None:
    signal = _aggregate([])

    assert signal.value == 0.0
    assert signal.weight == 0.0
    assert signal.source is SignalSource.NEWS


def test_bullish_items_produce_a_positive_signal() -> None:
    signal = _aggregate([_item(polarity=0.8), _item(polarity=0.6)])

    assert signal.value > 0


def test_opposing_items_cancel_out() -> None:
    signal = _aggregate([_item(polarity=1.0), _item(polarity=-1.0)])

    assert signal.value == pytest.approx(0.0)


def test_older_items_count_less_than_fresh_ones() -> None:
    fresh_wins = _aggregate(
        [
            _item(polarity=1.0),
            _item(polarity=-1.0, age=timedelta(hours=12)),
        ]
    )

    assert fresh_wins.value > 0


def test_an_item_exactly_one_half_life_old_counts_half() -> None:
    config = ContentConfig(news_half_life=timedelta(hours=6))
    aged = aggregate_sentiment(
        [_item(polarity=1.0, age=timedelta(hours=6))],
        symbol="BTC/USD",
        source=SignalSource.NEWS,
        now=NOW,
        config=config,
    )

    assert aged.weight == pytest.approx(0.5 / config.saturation)


def test_future_timestamps_are_not_amplified() -> None:
    signal = _aggregate([_item(polarity=1.0, age=timedelta(hours=-5))])

    assert signal.weight == pytest.approx(1.0 / ContentConfig().saturation)


def test_low_confidence_items_carry_less_weight() -> None:
    confident = _aggregate([_item(polarity=1.0, confidence=1.0)])
    unsure = _aggregate([_item(polarity=1.0, confidence=0.2)])

    assert confident.weight > unsure.weight


def test_authority_scales_influence() -> None:
    signal = _aggregate(
        [
            _item(polarity=1.0, authority=1.0),
            _item(polarity=-1.0, authority=0.1),
        ]
    )

    assert signal.value > 0


def test_weight_saturates_at_one() -> None:
    signal = _aggregate([_item(polarity=1.0) for _ in range(50)])

    assert signal.weight == 1.0


def test_evidence_lists_the_loudest_items_first() -> None:
    signal = _aggregate(
        [
            _item(polarity=0.1, label="quiet"),
            _item(polarity=0.9, label="loud"),
        ]
    )

    assert "loud" in signal.evidence[0]


def test_social_uses_a_shorter_half_life_than_news() -> None:
    aged = [_item(polarity=1.0, age=timedelta(hours=6))]
    news = _aggregate(aged, SignalSource.NEWS)
    social = _aggregate(aged, SignalSource.SOCIAL)

    assert social.weight < news.weight


def _news(event_id: str, title: str) -> NewsEvent:
    return NewsEvent(
        id=event_id,
        feed="https://example.test/rss",
        url=f"https://example.test/{event_id}",
        title=title,
        published_at=NOW,
        fetched_at=NOW,
    )


def _score(content_id: str, polarity: float) -> SentimentScore:
    return SentimentScore(
        content_id=content_id,
        model="lexicon-v1",
        polarity=polarity,
        confidence=1.0,
        scored_at=NOW,
    )


def _post(post_id: str, author_weight: float) -> SocialPost:
    return SocialPost(
        id=post_id,
        source=ContentSource.REDDIT,
        author="whale",
        url=f"https://reddit.test/{post_id}",
        body="body",
        created_at=NOW,
        fetched_at=NOW,
        author_weight=author_weight,
    )


def test_news_items_drops_unscored_events() -> None:
    events = [_news("a", "one"), _news("b", "two")]

    items = news_items(events, {"a": _score("a", 0.5)})

    assert len(items) == 1
    assert items[0].label == "one"


def test_social_items_gives_unknown_authors_a_floor_not_a_zero() -> None:
    config = ContentConfig(unknown_author_authority=0.2)

    items = social_items([_post("a", 0.0)], {"a": _score("a", 1.0)}, config)

    assert items[0].authority == pytest.approx(0.2)


def test_social_items_gives_curated_authors_full_authority() -> None:
    items = social_items([_post("a", 1.0)], {"a": _score("a", 1.0)})

    assert items[0].authority == pytest.approx(1.0)


def test_social_items_drops_unscored_posts() -> None:
    assert social_items([_post("a", 0.5)], {}) == ()
