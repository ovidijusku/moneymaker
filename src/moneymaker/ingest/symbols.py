"""Map free text onto the traded symbol universe.

Deliberately keyword-based rather than model-based: a wrong symbol tag silently
attributes sentiment to the wrong asset, so precision beats recall here.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from typing import Final

CRYPTO_KEYWORDS: Final[Mapping[str, tuple[str, ...]]] = {
    "BTC/USD": ("btc", "xbt", "bitcoin"),
    "ETH/USD": ("eth", "ether", "ethereum"),
    "SOL/USD": ("sol", "solana"),
    "XRP/USD": ("xrp", "ripple"),
    "DOGE/USD": ("doge", "dogecoin"),
    "ADA/USD": ("ada", "cardano"),
    "AVAX/USD": ("avax", "avalanche"),
    "LINK/USD": ("link", "chainlink"),
}

_PATTERNS: Final[Mapping[str, re.Pattern[str]]] = {
    symbol: re.compile(
        rf"\b(?:{'|'.join(re.escape(k) for k in keywords)})\b",
        re.IGNORECASE,
    )
    for symbol, keywords in CRYPTO_KEYWORDS.items()
}


def extract_symbols(text: str, universe: Collection[str] | None = None) -> frozenset[str]:
    """Return the symbols mentioned in `text`, restricted to `universe` if given."""
    if not text:
        return frozenset()
    candidates = _PATTERNS.keys() if universe is None else set(universe) & _PATTERNS.keys()
    return frozenset(symbol for symbol in candidates if _PATTERNS[symbol].search(text))
