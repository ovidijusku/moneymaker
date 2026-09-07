"""Map free text onto the traded symbol universe.

Deliberately keyword-based rather than model-based: a wrong symbol tag silently
attributes sentiment to the wrong asset, so precision beats recall here.

Tickers match case-sensitively, names case-insensitively. Without that split a
32-symbol universe is unusable: "link to the article" would tag LINK, "the yield
curve" would tag CRV, and every political headline would tag TRUMP.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from typing import Final

from moneymaker.universe import ASSETS

CRYPTO_KEYWORDS: Final[Mapping[str, tuple[str, ...]]] = {
    asset.symbol: asset.tickers + asset.aliases for asset in ASSETS
}


def _ticker_pattern(tickers: tuple[str, ...]) -> re.Pattern[str] | None:
    if not tickers:
        return None
    body = "|".join(re.escape(ticker) for ticker in tickers)
    return re.compile(rf"(?<![A-Za-z0-9])\$?(?:{body})(?![A-Za-z0-9])")


def _alias_pattern(aliases: tuple[str, ...]) -> re.Pattern[str] | None:
    if not aliases:
        return None
    body = "|".join(re.escape(alias) for alias in aliases)
    return re.compile(rf"\b(?:{body})\b", re.IGNORECASE)


_PATTERNS: Final[Mapping[str, tuple[re.Pattern[str] | None, re.Pattern[str] | None]]] = {
    asset.symbol: (_ticker_pattern(asset.tickers), _alias_pattern(asset.aliases))
    for asset in ASSETS
}


def _mentions(text: str, symbol: str) -> bool:
    ticker, alias = _PATTERNS[symbol]
    if ticker is not None and ticker.search(text):
        return True
    return alias is not None and alias.search(text) is not None


def extract_symbols(text: str, universe: Collection[str] | None = None) -> frozenset[str]:
    """Return the symbols mentioned in `text`, restricted to `universe` if given."""
    if not text:
        return frozenset()
    candidates = _PATTERNS.keys() if universe is None else set(universe) & _PATTERNS.keys()
    return frozenset(symbol for symbol in candidates if _mentions(text, symbol))
