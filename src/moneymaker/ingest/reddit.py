"""Reddit ingestion.

PRAW is synchronous, so submissions are pulled on a worker thread. The mapper is
pure and typed against a Protocol so tests need no Reddit client.
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Iterable, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from moneymaker.domain import ContentSource, SocialPost, content_id
from moneymaker.ingest.symbols import extract_symbols


@runtime_checkable
class Submission(Protocol):
    """The subset of a PRAW submission we depend on."""

    id: str
    title: str
    selftext: str
    permalink: str
    score: int
    created_utc: float

    @property
    def author(self) -> Any: ...


def _author_name(submission: Submission) -> str:
    author = submission.author
    return "[deleted]" if author is None else str(author)


def to_social_post(
    submission: Submission,
    *,
    fetched_at: datetime,
    author_weights: Mapping[str, float] | None = None,
    universe: Collection[str] | None = None,
) -> SocialPost:
    author = _author_name(submission)
    body = f"{submission.title}\n\n{submission.selftext}".strip()
    weights = author_weights or {}
    return SocialPost(
        id=content_id("reddit", submission.id),
        source=ContentSource.REDDIT,
        author=author,
        url=f"https://www.reddit.com{submission.permalink}",
        body=body,
        created_at=datetime.fromtimestamp(submission.created_utc, tz=UTC),
        fetched_at=fetched_at,
        score=submission.score,
        author_weight=weights.get(author.lower(), 0.0),
        symbols=extract_symbols(body, universe),
    )


def parse_submissions(
    submissions: Iterable[Submission],
    *,
    fetched_at: datetime,
    author_weights: Mapping[str, float] | None = None,
    universe: Collection[str] | None = None,
) -> tuple[SocialPost, ...]:
    return tuple(
        to_social_post(
            submission,
            fetched_at=fetched_at,
            author_weights=author_weights,
            universe=universe,
        )
        for submission in submissions
    )


async def fetch_subreddit(
    reddit: Any,
    subreddit: str,
    *,
    limit: int = 50,
    author_weights: Mapping[str, float] | None = None,
    universe: Collection[str] | None = None,
    now: datetime | None = None,
) -> tuple[SocialPost, ...]:
    def _pull() -> list[Submission]:
        return list(reddit.subreddit(subreddit).new(limit=limit))

    submissions = await asyncio.to_thread(_pull)
    return parse_submissions(
        submissions,
        fetched_at=now or datetime.now(tz=UTC),
        author_weights=author_weights,
        universe=universe,
    )
