"""The advice job: read stored data, score what is new, write advice.

All of the decision logic lives in `moneymaker.strategy.evaluate`; this module
only moves data in and out of the database.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from moneymaker.analysis.sentiment import MODEL_NAME, score_content
from moneymaker.domain import Advice, NewsEvent, SentimentScore, SocialPost
from moneymaker.persistence import (
    load_bars,
    load_news,
    load_posts,
    load_sentiment,
    store_advice,
    store_sentiment,
)
from moneymaker.pipeline.jobs import SessionFactory
from moneymaker.strategy.evaluate import StrategyConfig, evaluate

log = structlog.get_logger(__name__)


def _text(item: NewsEvent | SocialPost) -> str:
    if isinstance(item, NewsEvent):
        return f"{item.title}\n{item.body}"
    return item.body


async def _ensure_scored(
    session: AsyncSession,
    items: Sequence[NewsEvent | SocialPost],
    *,
    now: datetime,
) -> dict[str, SentimentScore]:
    """Score only what has no cached row, then persist the new scores."""
    cached = await load_sentiment(session, [item.id for item in items], model=MODEL_NAME)
    fresh = [
        score_content(item.id, _text(item), scored_at=now)
        for item in items
        if item.id not in cached
    ]
    if fresh:
        await store_sentiment(session, fresh)
    return cached | {score.content_id: score for score in fresh}


async def poll_advice(
    factory: SessionFactory,
    *,
    symbols: Sequence[str],
    config: StrategyConfig | None = None,
    now: datetime | None = None,
) -> int:
    settings = config or StrategyConfig()
    current = now or datetime.now(tz=UTC)
    content_since = current - settings.content_window
    history_since = current - settings.history_window

    advice: list[Advice] = []
    async with factory() as session:
        try:
            news = await load_news(session, since=content_since)
            posts = await load_posts(session, since=content_since)
            scores = await _ensure_scored(session, [*news, *posts], now=current)
        except Exception:
            log.exception("advice_content_load_failed")
            return 0

        for symbol in symbols:
            bars = await load_bars(session, symbol, since=history_since)
            result = evaluate(
                symbol=symbol,
                bars=bars,
                news=[item for item in news if symbol in item.symbols],
                posts=[item for item in posts if symbol in item.symbols],
                scores=scores,
                now=current,
                config=settings,
            )
            if result is None:
                log.info("advice_skipped_warming_up", symbol=symbol, bars=len(bars))
                continue
            advice.append(result)

        stored = await store_advice(session, advice)
        await session.commit()

    for item in advice:
        log.info(
            "advice",
            symbol=item.symbol,
            direction=item.direction.value,
            conviction=round(item.conviction, 3),
            rationale=item.rationale,
        )
    return stored
