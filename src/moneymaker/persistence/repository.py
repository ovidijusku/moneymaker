"""Write and read paths between domain objects and the database.

Every write is insert-or-ignore keyed on a natural id, so re-polling a feed or
replaying a backfill is idempotent.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Final, cast

from sqlalchemy import CursorResult, Insert, Table, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from moneymaker.domain import Bar, NewsEvent, SentimentScore, SocialPost
from moneymaker.persistence.schema import BarRow, NewsRow, SentimentRow, SocialRow

# DeclarativeBase types __table__ as FromClause; the dialect inserts need Table.
BAR_TABLE: Final[Table] = cast(Table, BarRow.__table__)
NEWS_TABLE: Final[Table] = cast(Table, NewsRow.__table__)
SOCIAL_TABLE: Final[Table] = cast(Table, SocialRow.__table__)
SENTIMENT_TABLE: Final[Table] = cast(Table, SentimentRow.__table__)


def _insert_ignore(dialect: str, table: Table, rows: Sequence[dict[str, Any]]) -> Insert:
    if dialect == "sqlite":
        return sqlite_insert(table).values(list(rows)).on_conflict_do_nothing()
    if dialect == "postgresql":
        return postgres_insert(table).values(list(rows)).on_conflict_do_nothing()
    raise NotImplementedError(f"insert-ignore is not implemented for dialect {dialect!r}")


async def _store(session: AsyncSession, table: Table, rows: Sequence[dict[str, Any]]) -> int:
    if not rows:
        return 0
    dialect = session.get_bind().dialect.name
    result = await session.execute(_insert_ignore(dialect, table, rows))
    return int(cast(CursorResult[Any], result).rowcount)


def _bar_values(bar: Bar) -> dict[str, Any]:
    return {
        "symbol": bar.symbol,
        "timestamp": bar.timestamp,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "trade_count": bar.trade_count,
        "vwap": bar.vwap,
    }


def _news_values(event: NewsEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "source": event.source.value,
        "feed": event.feed,
        "url": event.url,
        "title": event.title,
        "body": event.body,
        "published_at": event.published_at,
        "fetched_at": event.fetched_at,
        "symbols": sorted(event.symbols),
    }


def _social_values(post: SocialPost) -> dict[str, Any]:
    return {
        "id": post.id,
        "source": post.source.value,
        "author": post.author,
        "url": post.url,
        "body": post.body,
        "created_at": post.created_at,
        "fetched_at": post.fetched_at,
        "score": post.score,
        "author_weight": post.author_weight,
        "symbols": sorted(post.symbols),
    }


def _sentiment_values(score: SentimentScore) -> dict[str, Any]:
    return {
        "content_id": score.content_id,
        "model": score.model,
        "polarity": score.polarity,
        "confidence": score.confidence,
        "scored_at": score.scored_at,
    }


async def store_bars(session: AsyncSession, bars: Sequence[Bar]) -> int:
    return await _store(session, BAR_TABLE, [_bar_values(bar) for bar in bars])


async def store_news(session: AsyncSession, events: Sequence[NewsEvent]) -> int:
    return await _store(session, NEWS_TABLE, [_news_values(event) for event in events])


async def store_posts(session: AsyncSession, posts: Sequence[SocialPost]) -> int:
    return await _store(session, SOCIAL_TABLE, [_social_values(post) for post in posts])


async def store_sentiment(session: AsyncSession, scores: Sequence[SentimentScore]) -> int:
    return await _store(session, SENTIMENT_TABLE, [_sentiment_values(score) for score in scores])


async def latest_bar_timestamp(session: AsyncSession, symbol: str) -> datetime | None:
    """Resume point for backfill so we never re-download the whole history."""
    statement = select(BarRow.timestamp).where(BarRow.symbol == symbol)
    result = await session.execute(statement.order_by(BarRow.timestamp.desc()).limit(1))
    return result.scalar_one_or_none()


async def load_bars(
    session: AsyncSession,
    symbol: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> tuple[Bar, ...]:
    statement = select(BarRow).where(BarRow.symbol == symbol)
    if since is not None:
        statement = statement.where(BarRow.timestamp >= since)
    if until is not None:
        statement = statement.where(BarRow.timestamp < until)
    result = await session.execute(statement.order_by(BarRow.timestamp))
    return tuple(
        Bar(
            symbol=row.symbol,
            timestamp=row.timestamp,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            trade_count=row.trade_count,
            vwap=row.vwap,
        )
        for row in result.scalars()
    )
