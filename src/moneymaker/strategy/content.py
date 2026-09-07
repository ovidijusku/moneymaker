"""Turning scored news and social content into directional signals.

Old headlines are not wrong, they are priced in, so every item decays with a
source-specific half-life rather than dropping out of a fixed window.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from moneymaker.domain import (
    NewsEvent,
    SentimentScore,
    Signal,
    SignalSource,
    SocialPost,
)
from moneymaker.domain.types import SignedUnit, UnitInterval, UtcDatetime, clamp


class ScoredItem(BaseModel):
    """One scored piece of content, reduced to what the blend needs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: UtcDatetime
    polarity: SignedUnit
    confidence: UnitInterval
    #: Source credibility: 1.0 for a publisher, lower for an unvetted account.
    authority: UnitInterval = 1.0
    label: str = ""


class ContentConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    news_half_life: timedelta = timedelta(hours=6)
    social_half_life: timedelta = timedelta(hours=3)
    #: Credibility floor for an author who is not on the curated list.
    unknown_author_authority: float = Field(default=0.2, ge=0.0, le=1.0)
    #: Total decayed confidence at which the aggregate is fully trusted.
    saturation: float = Field(default=3.0, gt=0.0)


def _decay(age: timedelta, half_life: timedelta) -> float:
    if age <= timedelta(0):
        return 1.0
    return float(0.5 ** (age / half_life))


def news_items(
    events: Iterable[NewsEvent],
    scores: Mapping[str, SentimentScore],
) -> tuple[ScoredItem, ...]:
    return tuple(
        ScoredItem(
            timestamp=event.published_at,
            polarity=scores[event.id].polarity,
            confidence=scores[event.id].confidence,
            label=event.title,
        )
        for event in events
        if event.id in scores
    )


def social_items(
    posts: Iterable[SocialPost],
    scores: Mapping[str, SentimentScore],
    config: ContentConfig | None = None,
) -> tuple[ScoredItem, ...]:
    settings = config or ContentConfig()
    floor = settings.unknown_author_authority
    return tuple(
        ScoredItem(
            timestamp=post.created_at,
            polarity=scores[post.id].polarity,
            confidence=scores[post.id].confidence,
            # An unlisted author still counts, just not much.
            authority=floor + post.author_weight * (1.0 - floor),
            label=f"u/{post.author}",
        )
        for post in posts
        if post.id in scores
    )


def aggregate_sentiment(
    items: Sequence[ScoredItem],
    *,
    symbol: str,
    source: SignalSource,
    now: datetime,
    config: ContentConfig | None = None,
) -> Signal:
    """Blend scored content into one signal; a silent feed yields a zero signal."""
    settings = config or ContentConfig()
    half_life = (
        settings.social_half_life if source is SignalSource.SOCIAL else settings.news_half_life
    )

    total_weight = 0.0
    weighted = 0.0
    for item in items:
        weight = item.confidence * item.authority * _decay(now - item.timestamp, half_life)
        total_weight += weight
        weighted += weight * item.polarity

    value = clamp(weighted / total_weight) if total_weight > 0 else 0.0
    return Signal(
        symbol=symbol,
        timestamp=now,
        source=source,
        name=f"sentiment_{source.value}",
        value=value,
        weight=clamp(total_weight / settings.saturation, 0.0, 1.0),
        evidence=_evidence(items),
    )


def _evidence(items: Sequence[ScoredItem], limit: int = 3) -> tuple[str, ...]:
    loudest = sorted(items, key=lambda item: abs(item.polarity) * item.confidence, reverse=True)
    return tuple(
        f"{item.polarity:+.2f} {item.label}"[:120] for item in loudest[:limit] if item.label
    )
