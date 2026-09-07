"""Scheduled ingestion jobs.

Each job owns its own session and isolates per-source failures: one dead feed
must not stop the others or kill the scheduler.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from moneymaker.ingest.alpaca_bars import CryptoBarsClient, backfill
from moneymaker.ingest.reddit import fetch_subreddit
from moneymaker.ingest.rss import fetch_feed
from moneymaker.persistence import (
    latest_bar_timestamp,
    store_bars,
    store_news,
    store_posts,
)

log = structlog.get_logger(__name__)

SessionFactory = async_sessionmaker[AsyncSession]


async def _resume_start(
    session: AsyncSession,
    symbols: Sequence[str],
    *,
    now: datetime,
    lookback: timedelta,
) -> datetime:
    """Earliest point that leaves no gap for any symbol."""
    resumes = [await latest_bar_timestamp(session, symbol) for symbol in symbols]
    if any(resume is None for resume in resumes):
        return now - lookback
    return min(resume for resume in resumes if resume is not None) + timedelta(seconds=1)


async def poll_bars(
    factory: SessionFactory,
    client: CryptoBarsClient,
    *,
    symbols: Sequence[str],
    lookback: timedelta,
    now: datetime | None = None,
) -> int:
    current = now or datetime.now(tz=UTC)
    async with factory() as session:
        start = await _resume_start(session, symbols, now=current, lookback=lookback)
        try:
            bars = await backfill(client, symbols, start=start)
        except Exception:
            log.exception("bar_poll_failed", start=start.isoformat())
            return 0
        stored = await store_bars(session, bars)
        await session.commit()
    log.info("bars_polled", fetched=len(bars), stored=stored, since=start.isoformat())
    return stored


async def poll_news(
    factory: SessionFactory,
    client: httpx.AsyncClient,
    *,
    feeds: Sequence[str],
    universe: Sequence[str],
) -> int:
    stored = 0
    async with factory() as session:
        for url in feeds:
            try:
                events = await fetch_feed(client, url, feed=url, universe=universe)
            except Exception:
                log.exception("feed_poll_failed", feed=url)
                continue
            stored += await store_news(session, events)
        await session.commit()
    log.info("news_polled", stored=stored, feeds=len(feeds))
    return stored


async def poll_social(
    factory: SessionFactory,
    reddit: Any,
    *,
    subreddits: Sequence[str],
    limit: int,
    author_weights: Mapping[str, float],
    universe: Sequence[str],
) -> int:
    stored = 0
    async with factory() as session:
        for subreddit in subreddits:
            try:
                posts = await fetch_subreddit(
                    reddit,
                    subreddit,
                    limit=limit,
                    author_weights=author_weights,
                    universe=universe,
                )
            except Exception:
                log.exception("subreddit_poll_failed", subreddit=subreddit)
                continue
            stored += await store_posts(session, posts)
        await session.commit()
    log.info("social_polled", stored=stored, subreddits=len(subreddits))
    return stored
