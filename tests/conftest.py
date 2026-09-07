from __future__ import annotations

import pytest

from moneymaker.config import get_settings

_ENV_PREFIXES = (
    "ALPACA_",
    "REDDIT_",
    "TRADING_",
    "DATABASE_",
    "ENABLE_",
    "SYMBOLS",
    "RSS_",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop a developer's real shell environment from leaking into settings tests."""
    import os

    for key in list(os.environ):
        if key.startswith(_ENV_PREFIXES):
            monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
