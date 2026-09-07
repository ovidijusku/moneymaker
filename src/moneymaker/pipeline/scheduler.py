"""Scheduler wiring and the long-running ingestion loop."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from moneymaker.clients import (
    create_bars_client,
    create_http_client,
    create_reddit,
    create_trading_client,
)
from moneymaker.config import Settings
from moneymaker.persistence import create_engine, create_schema, create_session_factory
from moneymaker.pipeline.advice import poll_advice
from moneymaker.pipeline.jobs import SessionFactory, poll_bars, poll_news, poll_social
from moneymaker.pipeline.portfolio import poll_portfolio

log = structlog.get_logger(__name__)

# Overlapping polls would stack up behind a slow API, so each job runs alone.
_JOB_DEFAULTS = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 30}

# On a cold start the advice job would otherwise race the backfill, find no bars,
# and then sit idle for a whole interval before trying again.
_ADVICE_STARTUP_DELAY = timedelta(seconds=20)


def build_scheduler(
    settings: Settings,
    factory: SessionFactory,
    *,
    bars_client: Any,
    http_client: Any,
    reddit: Any | None,
    trading_client: Any = None,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    # Without this the first poll would not land until a full interval elapsed,
    # leaving a cold start with an empty database.
    start = datetime.now(tz=UTC)
    defaults = {**_JOB_DEFAULTS, "next_run_time": start}

    scheduler.add_job(
        partial(
            poll_bars,
            factory,
            bars_client,
            symbols=settings.symbols,
            lookback=settings.backfill_lookback,
        ),
        "interval",
        seconds=settings.bar_poll_seconds,
        id="bars",
        **defaults,
    )
    scheduler.add_job(
        partial(
            poll_news,
            factory,
            http_client,
            feeds=settings.rss_feeds,
            universe=settings.symbols,
        ),
        "interval",
        seconds=settings.news_poll_seconds,
        id="news",
        **defaults,
    )
    if reddit is not None:
        scheduler.add_job(
            partial(
                poll_social,
                factory,
                reddit,
                subreddits=settings.reddit_subreddits,
                limit=settings.reddit_post_limit,
                author_weights=settings.reddit_author_weights,
                universe=settings.symbols,
            ),
            "interval",
            seconds=settings.social_poll_seconds,
            id="social",
            **defaults,
        )
    scheduler.add_job(
        partial(poll_advice, factory, symbols=settings.symbols),
        "interval",
        seconds=settings.advice_poll_seconds,
        id="advice",
        **{**defaults, "next_run_time": start + _ADVICE_STARTUP_DELAY},
    )
    if trading_client is not None:
        scheduler.add_job(
            partial(poll_portfolio, factory, trading_client),
            "interval",
            seconds=settings.portfolio_poll_seconds,
            id="portfolio",
            **defaults,
        )
    return scheduler


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)


async def run(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    await create_schema(engine)
    factory = create_session_factory(engine)

    reddit = create_reddit(settings)
    if settings.enable_reddit and reddit is None:
        log.warning("reddit_disabled_missing_credentials")

    async with create_http_client() as http_client:
        scheduler = build_scheduler(
            settings,
            factory,
            bars_client=create_bars_client(settings),
            http_client=http_client,
            reddit=reddit,
            trading_client=create_trading_client(settings),
        )
        stop = asyncio.Event()
        _install_signal_handlers(stop)

        scheduler.start()
        log.info(
            "ingestion_started",
            mode=settings.trading_mode.value,
            symbols=list(settings.symbols),
            jobs=[job.id for job in scheduler.get_jobs()],
        )
        try:
            await stop.wait()
        finally:
            scheduler.shutdown(wait=True)
            await engine.dispose()
            log.info("ingestion_stopped")
