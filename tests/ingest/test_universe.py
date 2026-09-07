"""The tagger decides which asset a headline moves. Precision matters more than
recall here, and a 32-symbol universe is full of English words."""

from __future__ import annotations

import pytest

from moneymaker.ingest.symbols import extract_symbols
from moneymaker.universe import ASSETS, DEFAULT_SYMBOLS, STABLECOINS, display_name


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("BTC rallies past resistance", "BTC/USD"),
        ("$LINK oracle upgrade ships", "LINK/USD"),
        ("Bitcoin ETF inflows accelerate", "BTC/USD"),
        ("chainlink partners with a bank", "LINK/USD"),
        ("XBT futures open interest climbs", "BTC/USD"),
        ("MATIC rebrands", "POL/USD"),
    ],
)
def test_recognised_mentions(text: str, expected: str) -> None:
    assert expected in extract_symbols(text)


@pytest.mark.parametrize(
    "text",
    [
        "link to the article is broken",
        "the yield curve steepened again",
        "Trump said the economy is fine",
        "a rendering bug in the dashboard",
        "the sushi restaurant opened",
    ],
)
def test_english_words_are_not_tickers(text: str) -> None:
    """Case-sensitivity is the whole defence: lowercase prose must stay untagged."""
    assert extract_symbols(text) == frozenset()


def test_ticker_needs_a_boundary() -> None:
    assert extract_symbols("SOLANA1 is not a ticker") == frozenset()
    assert "SOL/USD" in extract_symbols("SOL closed higher")


def test_universe_restricts_results() -> None:
    text = "BTC and ETH both rallied"
    assert extract_symbols(text, universe=["BTC/USD"]) == frozenset({"BTC/USD"})


def test_empty_text_matches_nothing() -> None:
    assert extract_symbols("") == frozenset()


def test_universe_excludes_stablecoins() -> None:
    """Advice on a pegged asset is noise, so they never enter the universe."""
    assert not STABLECOINS & set(DEFAULT_SYMBOLS)


def test_universe_symbols_are_unique_usd_pairs() -> None:
    symbols = [asset.symbol for asset in ASSETS]
    assert len(symbols) == len(set(symbols))
    assert all(symbol.endswith("/USD") for symbol in symbols)


def test_display_name_falls_back_to_the_symbol() -> None:
    assert display_name("BTC/USD") == "Bitcoin"
    assert display_name("NOPE/USD") == "NOPE/USD"
