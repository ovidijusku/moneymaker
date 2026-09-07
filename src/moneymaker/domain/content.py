"""Ingested text content: news articles and social posts."""

from __future__ import annotations

import hashlib
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from moneymaker.domain.types import SignedUnit, Symbol, UnitInterval, UtcDatetime


def content_id(*parts: str) -> str:
    """Stable id used to deduplicate feed items and cache sentiment scores."""
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()
    return digest[:32]


class ContentSource(StrEnum):
    RSS = "rss"
    REDDIT = "reddit"
    X = "x"


class NewsEvent(BaseModel):
    """A published article. `published_at` drives backtests; `fetched_at` never does."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    source: ContentSource = ContentSource.RSS
    feed: str
    url: str
    title: str
    body: str = ""
    published_at: UtcDatetime
    fetched_at: UtcDatetime
    symbols: frozenset[Symbol] = frozenset()


class SocialPost(BaseModel):
    """A Reddit/X post. `author_weight` lets a curated allowlist outrank noise."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    source: ContentSource
    author: str
    url: str
    body: str
    created_at: UtcDatetime
    fetched_at: UtcDatetime
    score: int = 0
    author_weight: UnitInterval = 0.0
    symbols: frozenset[Symbol] = frozenset()


class SentimentScore(BaseModel):
    """Model output for one piece of content, keyed by its content id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    content_id: str
    model: str
    polarity: SignedUnit
    confidence: UnitInterval = Field(default=0.0)
    scored_at: UtcDatetime
