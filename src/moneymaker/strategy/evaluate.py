"""The whole strategy as one pure function.

Everything the decision depends on arrives as an argument, so the same call that
runs live replays exactly in a backtest. No clock, no database, no network.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from moneymaker.analysis.indicators import IndicatorConfig, compute_indicators
from moneymaker.domain import Advice, Bar, NewsEvent, SentimentScore, SignalSource, SocialPost
from moneymaker.strategy.composite import CompositeConfig, build_advice
from moneymaker.strategy.content import (
    ContentConfig,
    aggregate_sentiment,
    news_items,
    social_items,
)
from moneymaker.strategy.technical import TechnicalConfig, technical_signals


class StrategyConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    indicators: IndicatorConfig = Field(default_factory=IndicatorConfig)
    technical: TechnicalConfig = Field(default_factory=TechnicalConfig)
    content: ContentConfig = Field(default_factory=ContentConfig)
    composite: CompositeConfig = Field(default_factory=CompositeConfig)
    #: How far back news and social posts stay eligible.
    content_window: timedelta = timedelta(hours=24)
    #: How much bar history to load. Generous on purpose: gaps in the feed must
    #: not starve the indicators of their warm-up.
    history_window: timedelta = timedelta(hours=24)


def evaluate(
    *,
    symbol: str,
    bars: Sequence[Bar],
    news: Sequence[NewsEvent],
    posts: Sequence[SocialPost],
    scores: Mapping[str, SentimentScore],
    now: datetime,
    config: StrategyConfig | None = None,
) -> Advice | None:
    """Advice for one symbol, or None while the indicators are still warming up."""
    settings = config or StrategyConfig()
    snapshot = compute_indicators(bars, settings.indicators)
    if snapshot is None:
        return None

    signals = [
        *technical_signals(snapshot, settings.technical),
        aggregate_sentiment(
            news_items(news, scores),
            symbol=symbol,
            source=SignalSource.NEWS,
            now=now,
            config=settings.content,
        ),
        aggregate_sentiment(
            social_items(posts, scores, settings.content),
            symbol=symbol,
            source=SignalSource.SOCIAL,
            now=now,
            config=settings.content,
        ),
    ]
    return build_advice(
        symbol=symbol,
        # Stamped with the bar it was derived from, not the wall clock, so the
        # journal stays replayable and the advice row stays idempotent.
        timestamp=snapshot.timestamp,
        signals=signals,
        volatility=snapshot.volatility,
        config=settings.composite,
    )
