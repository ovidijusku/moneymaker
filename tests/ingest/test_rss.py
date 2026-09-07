from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from moneymaker.domain import ContentSource
from moneymaker.ingest.rss import fetch_feed, parse_entry, parse_feed

NOW = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)

FEED_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Test Feed</title>
  <item>
    <title>Bitcoin &amp; Ethereum rally</title>
    <link>https://example.com/a</link>
    <description>&lt;p&gt;BTC leads the move.&lt;/p&gt;</description>
    <pubDate>Thu, 01 Jan 2026 12:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Undated speculation</title>
    <link>https://example.com/b</link>
    <description>No publish date.</description>
  </item>
</channel></rss>
"""


def test_parse_entry_strips_html_and_unescapes_entities() -> None:
    entry = {
        "link": "https://example.com/a",
        "title": "Bitcoin &amp; friends",
        "summary": "<p>Big <b>move</b></p>",
        "published_parsed": (2026, 1, 1, 12, 0, 0, 0, 1, 0),
    }

    event = parse_entry(entry, feed="test", fetched_at=NOW)

    assert event is not None
    assert event.title == "Bitcoin & friends"
    assert event.body == "Big move"


def test_parse_entry_uses_published_date_not_fetch_time() -> None:
    entry = {
        "link": "https://example.com/a",
        "title": "Bitcoin",
        "published_parsed": (2026, 1, 1, 12, 0, 0, 0, 1, 0),
    }

    event = parse_entry(entry, feed="test", fetched_at=NOW)

    assert event is not None
    assert event.published_at == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert event.fetched_at == NOW


def test_parse_entry_falls_back_to_updated_date() -> None:
    entry = {
        "link": "https://example.com/a",
        "title": "Bitcoin",
        "updated_parsed": (2026, 1, 1, 12, 0, 0, 0, 1, 0),
    }

    event = parse_entry(entry, feed="test", fetched_at=NOW)

    assert event is not None
    assert event.published_at == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "entry",
    [
        {"title": "No link", "published_parsed": (2026, 1, 1, 12, 0, 0, 0, 1, 0)},
        {
            "link": "https://example.com/a",
            "published_parsed": (2026, 1, 1, 12, 0, 0, 0, 1, 0),
        },
        {"link": "https://example.com/a", "title": "No date"},
    ],
)
def test_parse_entry_drops_untrustworthy_entries(entry: dict[str, object]) -> None:
    assert parse_entry(entry, feed="test", fetched_at=NOW) is None


def test_parse_entry_tags_symbols_from_title_and_body() -> None:
    entry = {
        "link": "https://example.com/a",
        "title": "Bitcoin rallies",
        "summary": "solana follows",
        "published_parsed": (2026, 1, 1, 12, 0, 0, 0, 1, 0),
    }

    event = parse_entry(entry, feed="test", fetched_at=NOW)

    assert event is not None
    assert event.symbols == frozenset({"BTC/USD", "SOL/USD"})


def test_parse_entry_respects_symbol_universe() -> None:
    entry = {
        "link": "https://example.com/a",
        "title": "Bitcoin and solana",
        "published_parsed": (2026, 1, 1, 12, 0, 0, 0, 1, 0),
    }

    event = parse_entry(entry, feed="test", fetched_at=NOW, universe=["BTC/USD"])

    assert event is not None
    assert event.symbols == frozenset({"BTC/USD"})


def test_parse_feed_skips_entries_without_dates() -> None:
    events = parse_feed(FEED_XML, feed="test", fetched_at=NOW)

    assert [event.url for event in events] == ["https://example.com/a"]
    assert events[0].source is ContentSource.RSS


def test_same_url_yields_same_id_for_deduplication() -> None:
    first = parse_feed(FEED_XML, feed="test", fetched_at=NOW)
    second = parse_feed(FEED_XML, feed="test", fetched_at=datetime(2027, 1, 1, tzinfo=UTC))

    assert first[0].id == second[0].id


async def test_fetch_feed_parses_http_response() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=FEED_XML))

    async with httpx.AsyncClient(transport=transport) as client:
        events = await fetch_feed(client, "https://example.com/rss", feed="test", now=NOW)

    assert len(events) == 1
    assert events[0].title == "Bitcoin & Ethereum rally"


async def test_fetch_feed_raises_on_http_error() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(500))

    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_feed(client, "https://example.com/rss", feed="test", now=NOW)


async def test_fetch_feed_retries_transport_errors_then_succeeds() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, content=FEED_XML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        events = await fetch_feed(client, "https://example.com/rss", feed="test", now=NOW)

    assert attempts == 2
    assert len(events) == 1
