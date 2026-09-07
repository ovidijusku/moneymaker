from __future__ import annotations

import pytest

from moneymaker.ingest.symbols import extract_symbols


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Bitcoin hits a new high", {"BTC/USD"}),
        ("$BTC and $ETH rally together", {"BTC/USD", "ETH/USD"}),
        ("ethereum upgrade ships", {"ETH/USD"}),
        ("BTC/USD pair", {"BTC/USD"}),
    ],
)
def test_extracts_known_symbols(text: str, expected: set[str]) -> None:
    assert extract_symbols(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "the solution was ethical",  # must not match SOL or ETH
        "linkedin post about adaptation",  # must not match LINK or ADA
        "",
        "no tickers here",
    ],
)
def test_does_not_match_substrings_inside_words(text: str) -> None:
    assert extract_symbols(text) == frozenset()


def test_universe_restricts_results() -> None:
    text = "bitcoin and ethereum"

    assert extract_symbols(text, universe=["BTC/USD"]) == {"BTC/USD"}


def test_unknown_universe_entries_are_ignored() -> None:
    assert extract_symbols("bitcoin", universe=["NOPE/USD"]) == frozenset()


def test_matching_is_case_insensitive() -> None:
    assert extract_symbols("BiTcOiN") == {"BTC/USD"}
