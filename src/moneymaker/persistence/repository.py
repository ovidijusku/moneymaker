"""Write and read paths between domain objects and the database.

Every write is insert-or-ignore keyed on a natural id, so re-polling a feed or
replaying a backfill is idempotent.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Any, Final, cast

from sqlalchemy import CursorResult, Insert, Table, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from moneymaker.domain import (
    Advice,
    Bar,
    ContentSource,
    Direction,
    NewsEvent,
    Portfolio,
    Position,
    SentimentScore,
    Signal,
    SocialPost,
)
from moneymaker.persistence.schema import (
    AdviceRow,
    BarRow,
    NewsRow,
    PortfolioRow,
    SentimentRow,
    SocialRow,
)

# DeclarativeBase types __table__ as FromClause; the dialect inserts need Table.
BAR_TABLE: Final[Table] = cast(Table, BarRow.__table__)
NEWS_TABLE: Final[Table] = cast(Table, NewsRow.__table__)
SOCIAL_TABLE: Final[Table] = cast(Table, SocialRow.__table__)
SENTIMENT_TABLE: Final[Table] = cast(Table, SentimentRow.__table__)
ADVICE_TABLE: Final[Table] = cast(Table, AdviceRow.__table__)
PORTFOLIO_TABLE: Final[Table] = cast(Table, PortfolioRow.__table__)


def _insert_ignore(dialect: str, table: Table, rows: Sequence[dict[str, Any]]) -> Insert:
    if dialect == "sqlite":
        return sqlite_insert(table).values(list(rows)).on_conflict_do_nothing()
    if dialect == "postgresql":
        return postgres_insert(table).values(list(rows)).on_conflict_do_nothing()
    raise NotImplementedError(f"insert-ignore is not implemented for dialect {dialect!r}")


#: Postgres refuses a statement with more than 32767 bind parameters, and each
#: row spends one per column. A backfill across the full universe is tens of
#: thousands of bars, so a single INSERT is not an option.
MAX_BIND_PARAMS: Final[int] = 30000


def _chunk(table: Table, rows: Sequence[dict[str, Any]]) -> Iterator[Sequence[dict[str, Any]]]:
    size = max(1, MAX_BIND_PARAMS // max(len(table.columns), 1))
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


async def _store(session: AsyncSession, table: Table, rows: Sequence[dict[str, Any]]) -> int:
    if not rows:
        return 0
    dialect = session.get_bind().dialect.name
    stored = 0
    for batch in _chunk(table, rows):
        result = await session.execute(_insert_ignore(dialect, table, batch))
        stored += int(cast(CursorResult[Any], result).rowcount)
    return stored


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


def _advice_values(advice: Advice) -> dict[str, Any]:
    return {
        "symbol": advice.symbol,
        "timestamp": advice.timestamp,
        "direction": advice.direction.value,
        "conviction": advice.conviction,
        "rationale": advice.rationale,
        "signals": [signal.model_dump(mode="json") for signal in advice.signals],
    }


def _portfolio_values(portfolio: Portfolio) -> dict[str, Any]:
    return {
        "timestamp": portfolio.timestamp,
        "equity": portfolio.equity,
        "cash": portfolio.cash,
        "positions": [position.model_dump(mode="json") for position in portfolio.positions],
    }


async def store_bars(session: AsyncSession, bars: Sequence[Bar]) -> int:
    return await _store(session, BAR_TABLE, [_bar_values(bar) for bar in bars])


async def store_news(session: AsyncSession, events: Sequence[NewsEvent]) -> int:
    return await _store(session, NEWS_TABLE, [_news_values(event) for event in events])


async def store_posts(session: AsyncSession, posts: Sequence[SocialPost]) -> int:
    return await _store(session, SOCIAL_TABLE, [_social_values(post) for post in posts])


async def store_sentiment(session: AsyncSession, scores: Sequence[SentimentScore]) -> int:
    return await _store(session, SENTIMENT_TABLE, [_sentiment_values(score) for score in scores])


async def store_advice(session: AsyncSession, advice: Sequence[Advice]) -> int:
    return await _store(session, ADVICE_TABLE, [_advice_values(item) for item in advice])


async def store_portfolio(session: AsyncSession, portfolio: Portfolio) -> int:
    return await _store(session, PORTFOLIO_TABLE, [_portfolio_values(portfolio)])


async def latest_portfolio(session: AsyncSession) -> Portfolio | None:
    statement = select(PortfolioRow).order_by(PortfolioRow.timestamp.desc()).limit(1)
    result = await session.execute(statement)
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return Portfolio(
        timestamp=row.timestamp,
        equity=row.equity,
        cash=row.cash,
        positions=tuple(Position.model_validate(item) for item in row.positions),
    )


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


async def load_news(
    session: AsyncSession,
    *,
    since: datetime | None = None,
) -> tuple[NewsEvent, ...]:
    """All feeds at once. Symbol tags live in a JSON column, and filtering those
    in SQL is dialect-specific, so callers narrow by symbol in Python."""
    statement = select(NewsRow)
    if since is not None:
        statement = statement.where(NewsRow.published_at >= since)
    result = await session.execute(statement.order_by(NewsRow.published_at))
    return tuple(
        NewsEvent(
            id=row.id,
            source=ContentSource(row.source),
            feed=row.feed,
            url=row.url,
            title=row.title,
            body=row.body,
            published_at=row.published_at,
            fetched_at=row.fetched_at,
            symbols=frozenset(row.symbols),
        )
        for row in result.scalars()
    )


async def load_posts(
    session: AsyncSession,
    *,
    since: datetime | None = None,
) -> tuple[SocialPost, ...]:
    statement = select(SocialRow)
    if since is not None:
        statement = statement.where(SocialRow.created_at >= since)
    result = await session.execute(statement.order_by(SocialRow.created_at))
    return tuple(
        SocialPost(
            id=row.id,
            source=ContentSource(row.source),
            author=row.author,
            url=row.url,
            body=row.body,
            created_at=row.created_at,
            fetched_at=row.fetched_at,
            score=row.score,
            author_weight=row.author_weight,
            symbols=frozenset(row.symbols),
        )
        for row in result.scalars()
    )


async def load_sentiment(
    session: AsyncSession,
    content_ids: Sequence[str],
    *,
    model: str,
) -> dict[str, SentimentScore]:
    """Cached scores keyed by content id, so text is never scored twice."""
    if not content_ids:
        return {}
    statement = select(SentimentRow).where(
        SentimentRow.model == model,
        SentimentRow.content_id.in_(content_ids),
    )
    result = await session.execute(statement)
    return {
        row.content_id: SentimentScore(
            content_id=row.content_id,
            model=row.model,
            polarity=row.polarity,
            confidence=row.confidence,
            scored_at=row.scored_at,
        )
        for row in result.scalars()
    }


async def load_advice(
    session: AsyncSession,
    *,
    symbol: str | None = None,
    since: datetime | None = None,
) -> tuple[Advice, ...]:
    statement = select(AdviceRow)
    if symbol is not None:
        statement = statement.where(AdviceRow.symbol == symbol)
    if since is not None:
        statement = statement.where(AdviceRow.timestamp >= since)
    result = await session.execute(statement.order_by(AdviceRow.timestamp))
    return tuple(
        Advice(
            symbol=row.symbol,
            timestamp=row.timestamp,
            direction=Direction(row.direction),
            conviction=row.conviction,
            rationale=row.rationale,
            signals=tuple(Signal.model_validate(signal) for signal in row.signals),
        )
        for row in result.scalars()
    )
