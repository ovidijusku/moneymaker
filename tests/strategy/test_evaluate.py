from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from moneymaker.analysis.indicators import IndicatorConfig
from moneymaker.domain import (
    Bar,
    ContentSource,
    Direction,
    NewsEvent,
    SentimentScore,
    SignalSource,
    SocialPost,
)
from moneymaker.strategy.evaluate import StrategyConfig, evaluate

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
CONFIG = StrategyConfig(
    indicators=IndicatorConfig(
        ema_fast=3,
        ema_slow=5,
        rsi_period=3,
        atr_period=3,
        volume_lookback=3,
    )
)


def _bars(closes: list[float]) -> list[Bar]:
    return [
        Bar(
            symbol="BTC/USD",
            timestamp=NOW - timedelta(minutes=len(closes) - index),
            open=Decimal(str(close)),
            high=Decimal(str(close + 1)),
            low=Decimal(str(close - 1)),
            close=Decimal(str(close)),
            volume=Decimal("10"),
        )
        for index, close in enumerate(closes)
    ]


def _news(event_id: str, symbols: set[str]) -> NewsEvent:
    return NewsEvent(
        id=event_id,
        feed="https://feed.example",
        url=f"https://feed.example/{event_id}",
        title="headline",
        published_at=NOW,
        fetched_at=NOW,
        symbols=frozenset(symbols),
    )


def _post(post_id: str, symbols: set[str]) -> SocialPost:
    return SocialPost(
        id=post_id,
        source=ContentSource.REDDIT,
        author="someone",
        url=f"https://reddit.example/{post_id}",
        body="body",
        created_at=NOW,
        fetched_at=NOW,
        symbols=frozenset(symbols),
    )


def _score(content_id: str, polarity: float) -> SentimentScore:
    return SentimentScore(
        content_id=content_id,
        model="lexicon-v1",
        polarity=polarity,
        confidence=1.0,
        scored_at=NOW,
    )


def test_returns_none_while_indicators_are_warming_up() -> None:
    advice = evaluate(
        symbol="BTC/USD",
        bars=_bars([100.0, 101.0]),
        news=[],
        posts=[],
        scores={},
        now=NOW,
        config=CONFIG,
    )

    assert advice is None


def test_produces_advice_once_there_is_enough_history() -> None:
    advice = evaluate(
        symbol="BTC/USD",
        bars=_bars([100.0 + i for i in range(20)]),
        news=[],
        posts=[],
        scores={},
        now=NOW,
        config=CONFIG,
    )

    assert advice is not None
    assert advice.symbol == "BTC/USD"
    assert advice.direction in set(Direction)


def test_advice_carries_all_four_signal_sources() -> None:
    advice = evaluate(
        symbol="BTC/USD",
        bars=_bars([100.0 + i for i in range(20)]),
        news=[],
        posts=[],
        scores={},
        now=NOW,
        config=CONFIG,
    )

    assert advice is not None
    sources = {signal.source for signal in advice.signals}
    assert sources == {SignalSource.TECHNICAL, SignalSource.NEWS, SignalSource.SOCIAL}


def test_advice_is_stamped_with_the_last_bar_not_the_clock() -> None:
    bars = _bars([100.0 + i for i in range(20)])

    advice = evaluate(
        symbol="BTC/USD",
        bars=bars,
        news=[],
        posts=[],
        scores={},
        now=NOW + timedelta(hours=3),
        config=CONFIG,
    )

    assert advice is not None
    assert advice.timestamp == bars[-1].timestamp


def test_bullish_news_pushes_the_score_up() -> None:
    bars = _bars([100.0] * 20)
    news = [_news("a", {"BTC/USD"})]

    neutral = evaluate(
        symbol="BTC/USD",
        bars=bars,
        news=[],
        posts=[],
        scores={},
        now=NOW,
        config=CONFIG,
    )
    positive = evaluate(
        symbol="BTC/USD",
        bars=bars,
        news=news,
        posts=[],
        scores={"a": _score("a", 1.0)},
        now=NOW,
        config=CONFIG,
    )

    assert neutral is not None
    assert positive is not None
    news_signal = next(s for s in positive.signals if s.source is SignalSource.NEWS)
    assert news_signal.value > 0
    assert news_signal.weight > 0


def test_unscored_content_contributes_nothing() -> None:
    advice = evaluate(
        symbol="BTC/USD",
        bars=_bars([100.0] * 20),
        news=[_news("a", {"BTC/USD"})],
        posts=[_post("b", {"BTC/USD"})],
        scores={},
        now=NOW,
        config=CONFIG,
    )

    assert advice is not None
    for signal in advice.signals:
        if signal.source is not SignalSource.TECHNICAL:
            assert signal.weight == 0.0


def test_default_config_is_usable() -> None:
    advice = evaluate(
        symbol="BTC/USD",
        bars=_bars([100.0 + i for i in range(60)]),
        news=[],
        posts=[],
        scores={},
        now=NOW,
    )

    assert advice is not None
