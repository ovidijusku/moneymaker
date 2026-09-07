"""Shared test doubles for the external services we integrate with."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

CREATED = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@dataclass
class FakeAlpacaBar:
    symbol: str = "BTC/USD"
    timestamp: datetime = CREATED
    open: float = 100.1
    high: float = 110.0
    low: float = 90.0
    close: float = 105.0
    volume: float = 3.5
    trade_count: float | None = 12.0
    vwap: float | None = 101.25


@dataclass
class FakeBarSet:
    data: dict[str, list[FakeAlpacaBar]]


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
    def __init__(
        self,
        submissions: list[FakeSubmission],
        failing: set[str] | None = None,
    ) -> None:
        self._submissions = submissions
        self._failing = failing or set()
        self.requested: list[str] = []

    def subreddit(self, name: str) -> FakeListing:
        self.requested.append(name)
        if name in self._failing:
            raise RuntimeError("subreddit unavailable")
        return FakeListing(self._submissions)


@dataclass
class FakeBarsClient:
    bars: list[FakeAlpacaBar] = field(default_factory=list)
    requests: list[Any] = field(default_factory=list)
    error: Exception | None = None
    symbol: str = "BTC/USD"

    def get_crypto_bars(self, request_params: Any) -> FakeBarSet:
        self.requests.append(request_params)
        if self.error is not None:
            raise self.error
        return FakeBarSet({self.symbol: self.bars})
