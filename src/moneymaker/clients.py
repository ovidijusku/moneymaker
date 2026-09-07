"""External client construction. The only place credentials leave Settings."""

from __future__ import annotations

from typing import Any

import httpx
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.trading.client import TradingClient

from moneymaker.config import Settings
from moneymaker.ingest.rss import USER_AGENT

_HTTP_TIMEOUT = httpx.Timeout(15.0)


def create_bars_client(settings: Settings) -> CryptoHistoricalDataClient:
    return CryptoHistoricalDataClient(
        api_key=settings.alpaca_api_key.get_secret_value(),
        secret_key=settings.alpaca_api_secret.get_secret_value(),
    )


def create_trading_client(settings: Settings) -> TradingClient:
    """Used read-only, for account and position state. This project submits no orders."""
    return TradingClient(
        api_key=settings.alpaca_api_key.get_secret_value(),
        secret_key=settings.alpaca_api_secret.get_secret_value(),
        paper=settings.alpaca_paper,
    )


def create_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )


def create_reddit(settings: Settings) -> Any | None:
    """None when Reddit is disabled, so callers skip the job entirely."""
    if not settings.enable_reddit:
        return None
    if settings.reddit_client_id is None or settings.reddit_client_secret is None:
        return None

    import praw

    return praw.Reddit(
        client_id=settings.reddit_client_id.get_secret_value(),
        client_secret=settings.reddit_client_secret.get_secret_value(),
        user_agent=settings.reddit_user_agent,
        # PRAW is called from a worker thread, so its asyncio guard is noise.
        check_for_async=False,
    )
