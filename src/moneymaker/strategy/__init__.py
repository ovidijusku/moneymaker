"""Strategy layer: pure signal-to-advice logic. No I/O, no persistence."""

from moneymaker.strategy.composite import CompositeConfig, blend, build_advice
from moneymaker.strategy.content import (
    ContentConfig,
    ScoredItem,
    aggregate_sentiment,
    news_items,
    social_items,
)
from moneymaker.strategy.technical import TechnicalConfig, technical_signals

__all__ = [
    "CompositeConfig",
    "ContentConfig",
    "ScoredItem",
    "TechnicalConfig",
    "aggregate_sentiment",
    "blend",
    "build_advice",
    "news_items",
    "social_items",
    "technical_signals",
]
