"""One chronological feed across every symbol.

News, social chatter and our own advice are three different tables but one
story. Interleaving them is what makes a headline and the opinion it moved
readable side by side.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from moneymaker.domain import Advice, Direction, NewsEvent, SocialPost
from moneymaker.universe import display_name

EventKind = Literal["news", "social", "advice"]

#: Long enough to identify the item, short enough to scan.
_SUMMARY_CHARS = 280


def _summarise(text: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= _SUMMARY_CHARS:
        return cleaned
    return cleaned[: _SUMMARY_CHARS - 1].rstrip() + "\u2026"


class StreamEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: EventKind
    timestamp: datetime
    symbols: tuple[str, ...]
    #: Human-readable asset names, so the UI does not have to own the mapping.
    names: tuple[str, ...]
    title: str
    summary: str = ""
    source: str = ""
    url: str | None = None
    direction: Direction | None = None
    conviction: float | None = None


def _named(symbols: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(display_name(symbol) for symbol in symbols)


def from_news(event: NewsEvent) -> StreamEvent:
    symbols = tuple(sorted(event.symbols))
    return StreamEvent(
        id=f"news:{event.id}",
        kind="news",
        timestamp=event.published_at,
        symbols=symbols,
        names=_named(symbols),
        title=event.title,
        summary=_summarise(event.body),
        source=event.feed,
        url=event.url,
    )


def from_post(post: SocialPost) -> StreamEvent:
    symbols = tuple(sorted(post.symbols))
    return StreamEvent(
        id=f"social:{post.id}",
        kind="social",
        timestamp=post.created_at,
        symbols=symbols,
        names=_named(symbols),
        title=_summarise(post.body)[:120] or f"post by {post.author}",
        summary=_summarise(post.body),
        source=post.author,
        url=post.url,
    )


def from_advice(advice: Advice) -> StreamEvent:
    symbols = (advice.symbol,)
    return StreamEvent(
        id=f"advice:{advice.symbol}:{advice.timestamp.isoformat()}",
        kind="advice",
        timestamp=advice.timestamp,
        symbols=symbols,
        names=_named(symbols),
        title=f"{advice.direction.value.upper()} {display_name(advice.symbol)}",
        summary=advice.rationale,
        source="strategy",
        direction=advice.direction,
        conviction=advice.conviction,
    )


def build_stream(
    *,
    news: tuple[NewsEvent, ...] = (),
    posts: tuple[SocialPost, ...] = (),
    advice: tuple[Advice, ...] = (),
    symbols: frozenset[str] | None = None,
    limit: int = 100,
) -> list[StreamEvent]:
    """Newest first. Untagged news is dropped when a symbol filter is given,
    but kept otherwise -- market-wide headlines still matter."""
    events = [
        *(from_news(item) for item in news),
        *(from_post(item) for item in posts),
        *(from_advice(item) for item in advice),
    ]
    if symbols is not None:
        events = [event for event in events if symbols & set(event.symbols)]
    events.sort(key=lambda event: event.timestamp, reverse=True)
    return events[:limit]
