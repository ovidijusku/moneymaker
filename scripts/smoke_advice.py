"""Read-only advisory dry run against whatever is already in the database.

Computes indicators from stored bars, scores stored headlines with the lexicon,
blends both into advice, and prints it. Writes nothing and places no orders.

Run with: uv run python scripts/smoke_advice.py
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from moneymaker.analysis import compute_indicators
from moneymaker.analysis.sentiment import score_content
from moneymaker.config import get_settings
from moneymaker.domain import NewsEvent, SignalSource
from moneymaker.persistence import create_engine, create_session_factory, load_bars
from moneymaker.persistence.schema import NewsRow
from moneymaker.strategy import aggregate_sentiment, build_advice, technical_signals
from moneymaker.strategy.content import news_items


async def _recent_news(session: AsyncSession, symbol: str) -> tuple[NewsEvent, ...]:
    statement = select(NewsRow).order_by(NewsRow.published_at.desc()).limit(50)
    result = await session.execute(statement)
    return tuple(
        NewsEvent(
            id=row.id,
            source=row.source,
            feed=row.feed,
            url=row.url,
            title=row.title,
            body=row.body,
            published_at=row.published_at,
            fetched_at=row.fetched_at,
            symbols=frozenset(row.symbols),
        )
        for row in result.scalars()
        if symbol in row.symbols
    )


async def main() -> int:
    settings = get_settings()
    now = datetime.now(tz=UTC)
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)

    async with factory() as session:
        for symbol in settings.symbols:
            bars = await load_bars(session, symbol)
            snapshot = compute_indicators(bars)
            if snapshot is None:
                print(f"{symbol}: only {len(bars)} bars, indicators still warming up")
                continue

            events = await _recent_news(session, symbol)
            scores = {
                event.id: score_content(event.id, f"{event.title} {event.body}", scored_at=now)
                for event in events
            }
            news = aggregate_sentiment(
                news_items(events, scores),
                symbol=symbol,
                source=SignalSource.NEWS,
                now=now,
            )
            signals = [*technical_signals(snapshot), news]
            advice = build_advice(
                symbol=symbol,
                timestamp=snapshot.timestamp,
                signals=signals,
                volatility=snapshot.volatility,
            )

            print(f"\n{symbol}  bars={len(bars)}  news={len(events)}")
            print(
                f"  close={snapshot.close:.2f} rsi={snapshot.rsi:.1f} "
                f"spread={snapshot.ema_spread:+.3%} vol={snapshot.volatility:.3%}"
            )
            print(f"  -> {advice.direction.value.upper()} conviction={advice.conviction:.2f}")
            print(f"     {advice.rationale}")
            for signal in signals:
                for line in signal.evidence:
                    print(f"     - {line}")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
