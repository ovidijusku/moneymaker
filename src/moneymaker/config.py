"""Application settings. Every external dependency is validated at import time."""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(StrEnum):
    ADVISORY = "advisory"
    PAPER = "paper"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        frozen=True,
    )

    trading_mode: TradingMode = TradingMode.ADVISORY

    alpaca_api_key: SecretStr
    alpaca_api_secret: SecretStr
    alpaca_paper: bool = True

    database_url: str = "sqlite+aiosqlite:///./data/moneymaker.db"
    log_level: str = "INFO"

    symbols: tuple[str, ...] = ("BTC/USD", "ETH/USD")

    enable_reddit: bool = False
    reddit_client_id: SecretStr | None = None
    reddit_client_secret: SecretStr | None = None
    reddit_user_agent: str = "moneymaker/0.1"
    reddit_subreddits: tuple[str, ...] = ("CryptoCurrency", "CryptoMarkets", "Bitcoin")
    reddit_post_limit: int = Field(default=50, ge=1, le=100)
    #: Curated allowlist; unlisted authors score 0 and contribute nothing.
    reddit_author_weights: dict[str, float] = Field(default_factory=dict)

    # X/Twitter read access is paid and its ToS forbids scraping; off by default.
    enable_x: bool = False

    rss_feeds: tuple[str, ...] = (
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
    )

    #: Must be set to True explicitly before real capital is ever at risk.
    acknowledge_live_trading_risk: bool = Field(default=False)

    bar_poll_seconds: int = Field(default=60, ge=5)
    news_poll_seconds: int = Field(default=300, ge=30)
    social_poll_seconds: int = Field(default=300, ge=30)
    advice_poll_seconds: int = Field(default=300, ge=30)
    backfill_lookback_hours: int = Field(default=24, ge=1)

    @property
    def backfill_lookback(self) -> timedelta:
        return timedelta(hours=self.backfill_lookback_hours)

    @field_validator("reddit_author_weights")
    @classmethod
    def normalise_author_keys(cls, value: dict[str, float]) -> dict[str, float]:
        return {author.lower(): weight for author, weight in value.items()}

    @field_validator("symbols", "rss_feeds")
    @classmethod
    def reject_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("must contain at least one entry")
        return value

    @model_validator(mode="after")
    def check_mode_prerequisites(self) -> Settings:
        if self.enable_reddit and not (self.reddit_client_id and self.reddit_client_secret):
            raise ValueError("enable_reddit requires reddit_client_id and reddit_client_secret")
        if self.trading_mode is TradingMode.LIVE:
            if self.alpaca_paper:
                raise ValueError("live trading_mode requires alpaca_paper=False")
            if not self.acknowledge_live_trading_risk:
                raise ValueError("live trading_mode requires acknowledge_live_trading_risk=True")
        return self

    @property
    def executes_orders(self) -> bool:
        return self.trading_mode is not TradingMode.ADVISORY


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
