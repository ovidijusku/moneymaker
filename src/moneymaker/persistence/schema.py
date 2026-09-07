"""Database schema. Rows are dumb storage; the domain models hold the rules."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from moneymaker.persistence.types import ExactDecimal, UtcTimestamp


class Base(DeclarativeBase):
    pass


class BarRow(Base):
    __tablename__ = "bars"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(UtcTimestamp, primary_key=True)
    open: Mapped[Decimal] = mapped_column(ExactDecimal)
    high: Mapped[Decimal] = mapped_column(ExactDecimal)
    low: Mapped[Decimal] = mapped_column(ExactDecimal)
    close: Mapped[Decimal] = mapped_column(ExactDecimal)
    volume: Mapped[Decimal] = mapped_column(ExactDecimal)
    trade_count: Mapped[int] = mapped_column(Integer, default=0)
    vwap: Mapped[Decimal | None] = mapped_column(ExactDecimal, nullable=True)


class NewsRow(Base):
    __tablename__ = "news_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[str] = mapped_column(String(16))
    feed: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(String(1024))
    title: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(String, default="")
    published_at: Mapped[datetime] = mapped_column(UtcTimestamp)
    fetched_at: Mapped[datetime] = mapped_column(UtcTimestamp)
    symbols: Mapped[list[str]] = mapped_column(JSON, default=list)

    __table_args__ = (Index("ix_news_published_at", "published_at"),)


class SocialRow(Base):
    __tablename__ = "social_posts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[str] = mapped_column(String(16))
    author: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(1024))
    body: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(UtcTimestamp)
    fetched_at: Mapped[datetime] = mapped_column(UtcTimestamp)
    score: Mapped[int] = mapped_column(Integer, default=0)
    author_weight: Mapped[float] = mapped_column(default=0.0)
    symbols: Mapped[list[str]] = mapped_column(JSON, default=list)

    __table_args__ = (Index("ix_social_created_at", "created_at"),)


class SentimentRow(Base):
    __tablename__ = "sentiment_scores"

    content_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    model: Mapped[str] = mapped_column(String(64), primary_key=True)
    polarity: Mapped[float] = mapped_column()
    confidence: Mapped[float] = mapped_column(default=0.0)
    scored_at: Mapped[datetime] = mapped_column(UtcTimestamp)


class AdviceRow(Base):
    """The advice journal. Keyed on the bar it was derived from, so re-running
    the job never rewrites history -- the first opinion recorded stands."""

    __tablename__ = "advice"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(UtcTimestamp, primary_key=True)
    direction: Mapped[str] = mapped_column(String(8))
    conviction: Mapped[float] = mapped_column(default=0.0)
    rationale: Mapped[str] = mapped_column(String, default="")
    signals: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)

    __table_args__ = (Index("ix_advice_timestamp", "timestamp"),)
