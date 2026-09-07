"""RSS/Atom news ingestion.

`parse_entry` is pure so feed handling can be tested against recorded fixtures;
only `fetch_feed` touches the network.
"""

from __future__ import annotations

import calendar
import html
import re
import time
from collections.abc import Collection, Mapping
from datetime import UTC, datetime
from typing import Any, Final

import feedparser
import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from moneymaker.domain import ContentSource, NewsEvent, content_id
from moneymaker.ingest.symbols import extract_symbols

USER_AGENT: Final = "moneymaker/0.1"
DEFAULT_TIMEOUT: Final = httpx.Timeout(10.0)
_TAG_RE: Final = re.compile(r"<[^>]+>")


def _strip_html(value: str) -> str:
    return html.unescape(_TAG_RE.sub("", value)).strip()


def _published_at(entry: Mapping[str, Any]) -> datetime | None:
    parsed: time.struct_time | None = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)


def parse_entry(
    entry: Mapping[str, Any],
    *,
    feed: str,
    fetched_at: datetime,
    universe: Collection[str] | None = None,
) -> NewsEvent | None:
    """Return None for entries we cannot trust rather than guessing values.

    A missing publish date is dropped instead of defaulting to now: backtests
    key off `published_at`, and a wrong one manufactures look-ahead bias.
    """
    url = str(entry.get("link") or "").strip()
    title = _strip_html(str(entry.get("title") or ""))
    published_at = _published_at(entry)
    if not url or not title or published_at is None:
        return None

    body = _strip_html(str(entry.get("summary") or ""))
    return NewsEvent(
        id=content_id(url),
        source=ContentSource.RSS,
        feed=feed,
        url=url,
        title=title,
        body=body,
        published_at=published_at,
        fetched_at=fetched_at,
        symbols=extract_symbols(f"{title} {body}", universe),
    )


def parse_feed(
    payload: bytes,
    *,
    feed: str,
    fetched_at: datetime,
    universe: Collection[str] | None = None,
) -> tuple[NewsEvent, ...]:
    parsed = feedparser.parse(payload)
    events = (
        parse_entry(entry, feed=feed, fetched_at=fetched_at, universe=universe)
        for entry in parsed.entries
    )
    return tuple(event for event in events if event is not None)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    retry=retry_if_exception_type(httpx.TransportError),
    reraise=True,
)
async def _get(client: httpx.AsyncClient, url: str) -> bytes:
    response = await client.get(url, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.content


async def fetch_feed(
    client: httpx.AsyncClient,
    url: str,
    *,
    feed: str,
    universe: Collection[str] | None = None,
    now: datetime | None = None,
) -> tuple[NewsEvent, ...]:
    payload = await _get(client, url)
    fetched_at = now or datetime.now(tz=UTC)
    return parse_feed(payload, feed=feed, fetched_at=fetched_at, universe=universe)
