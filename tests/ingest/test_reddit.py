from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from moneymaker.domain import ContentSource
from moneymaker.ingest.reddit import fetch_subreddit, parse_submissions, to_social_post

NOW = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
CREATED = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@dataclass
class FakeSubmission:
    id: str = "abc123"
    title: str = "Bitcoin looks strong"
    selftext: str = "accumulating here"
    permalink: str = "/r/CryptoCurrency/comments/abc123/"
    score: int = 120
    created_utc: float = CREATED.timestamp()
    author: Any = "WhaleWatcher"


class FakeListing:
    def __init__(self, submissions: list[FakeSubmission]) -> None:
        self._submissions = submissions

    def new(self, limit: int) -> list[FakeSubmission]:
        return self._submissions[:limit]


class FakeReddit:
    def __init__(self, submissions: list[FakeSubmission]) -> None:
        self._submissions = submissions
        self.requested: list[str] = []

    def subreddit(self, name: str) -> FakeListing:
        self.requested.append(name)
        return FakeListing(self._submissions)


def test_maps_submission_to_social_post() -> None:
    post = to_social_post(FakeSubmission(), fetched_at=NOW)

    assert post.source is ContentSource.REDDIT
    assert post.author == "WhaleWatcher"
    assert post.url == "https://www.reddit.com/r/CryptoCurrency/comments/abc123/"
    assert post.created_at == CREATED
    assert post.score == 120
    assert post.symbols == frozenset({"BTC/USD"})


def test_deleted_author_does_not_crash_mapping() -> None:
    post = to_social_post(FakeSubmission(author=None), fetched_at=NOW)

    assert post.author == "[deleted]"


def test_author_weight_lookup_is_case_insensitive() -> None:
    post = to_social_post(
        FakeSubmission(),
        fetched_at=NOW,
        author_weights={"whalewatcher": 0.9},
    )

    assert post.author_weight == 0.9


def test_unlisted_author_gets_zero_weight() -> None:
    post = to_social_post(FakeSubmission(), fetched_at=NOW, author_weights={"someoneelse": 0.9})

    assert post.author_weight == 0.0


def test_post_id_is_stable_across_polls() -> None:
    first = to_social_post(FakeSubmission(), fetched_at=NOW)
    second = to_social_post(FakeSubmission(score=999), fetched_at=datetime(2027, 1, 1, tzinfo=UTC))

    assert first.id == second.id


def test_parse_submissions_maps_all_entries() -> None:
    posts = parse_submissions(
        [FakeSubmission(id="a"), FakeSubmission(id="b")],
        fetched_at=NOW,
    )

    assert len({post.id for post in posts}) == 2


async def test_fetch_subreddit_respects_limit() -> None:
    reddit = FakeReddit([FakeSubmission(id=str(index)) for index in range(10)])

    posts = await fetch_subreddit(reddit, "CryptoCurrency", limit=3, now=NOW)

    assert len(posts) == 3
