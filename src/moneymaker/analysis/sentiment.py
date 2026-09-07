"""Lexicon sentiment scoring.

A deliberately small, deterministic baseline: no model download, no GPU, and it
runs in microseconds so it can score every headline on every poll. It is also
genuinely weak -- it cannot read sarcasm, context, or a chart in an image.

The `sentiment` extra exists to swap a transformer in behind the same
`score_content` shape once the advice journal shows the lexicon is the
bottleneck. Until there is evidence of that, this stays.
"""

from __future__ import annotations

import re
from datetime import datetime

from moneymaker.domain import SentimentScore
from moneymaker.domain.types import clamp

MODEL_NAME = "lexicon-v1"

BULLISH = frozenset(
    {
        "accumulate",
        "adoption",
        "approval",
        "approved",
        "breakout",
        "bullish",
        "buy",
        "gain",
        "gains",
        "growth",
        "inflow",
        "inflows",
        "long",
        "moon",
        "partnership",
        "rally",
        "rebound",
        "record",
        "rise",
        "rises",
        "soar",
        "soars",
        "support",
        "surge",
        "surges",
        "upgrade",
        "upside",
    }
)

BEARISH = frozenset(
    {
        "ban",
        "bearish",
        "breakdown",
        "capitulation",
        "collapse",
        "crash",
        "decline",
        "delisting",
        "downgrade",
        "downside",
        "dump",
        "exploit",
        "fraud",
        "hack",
        "hacked",
        "lawsuit",
        "liquidated",
        "liquidation",
        "loss",
        "losses",
        "outflow",
        "outflows",
        "plunge",
        "plunges",
        "rug",
        "scam",
        "sell",
        "selloff",
        "short",
        "slump",
        "tumble",
        "warning",
    }
)

NEGATIONS = frozenset(
    {
        "aint",
        "arent",
        "cannot",
        "cant",
        "didnt",
        "dont",
        "isnt",
        "never",
        "no",
        "not",
        "wasnt",
        "wont",
    }
)

#: Matched terms at which the score is considered fully informed.
SATURATION = 4

#: How many tokens back a negation still applies.
NEGATION_WINDOW = 3

_TOKEN = re.compile(r"[a-z']+")


def _tokenise(text: str) -> list[str]:
    return [token.replace("'", "") for token in _TOKEN.findall(text.lower())]


def score_text(text: str) -> tuple[float, float]:
    """Return (polarity, confidence). Both are 0.0 when nothing matched."""
    tokens = _tokenise(text)
    bullish = 0
    bearish = 0
    for index, token in enumerate(tokens):
        if token not in BULLISH and token not in BEARISH:
            continue
        positive = token in BULLISH
        # "not a scam" is not bearish. A short window catches the intervening
        # articles and adverbs without reaching into the previous clause.
        window = tokens[max(0, index - NEGATION_WINDOW) : index]
        if any(word in NEGATIONS for word in window):
            positive = not positive
        if positive:
            bullish += 1
        else:
            bearish += 1

    hits = bullish + bearish
    if hits == 0:
        return 0.0, 0.0
    polarity = clamp((bullish - bearish) / hits)
    confidence = clamp(hits / SATURATION, 0.0, 1.0)
    return polarity, confidence


def score_content(content_id: str, text: str, *, scored_at: datetime) -> SentimentScore:
    polarity, confidence = score_text(text)
    return SentimentScore(
        content_id=content_id,
        model=MODEL_NAME,
        polarity=polarity,
        confidence=confidence,
        scored_at=scored_at,
    )
