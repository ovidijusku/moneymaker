from __future__ import annotations

import pytest
from pydantic import ValidationError

from moneymaker.config import Settings, TradingMode, get_settings

SENTINEL_SECRET = "sentinel-4f3a9c"  # noqa: S105

BASE_ENV = {
    "alpaca_api_key": "key",
    "alpaca_api_secret": SENTINEL_SECRET,
}


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **{**BASE_ENV, **overrides})  # type: ignore[arg-type, call-arg]


def test_defaults_to_advisory_mode_without_execution() -> None:
    settings = make_settings()

    assert settings.trading_mode is TradingMode.ADVISORY
    assert not settings.executes_orders


def test_missing_alpaca_credentials_fail_fast() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_secret_values_are_not_exposed_when_rendered() -> None:
    settings = make_settings()

    assert SENTINEL_SECRET not in repr(settings)
    assert SENTINEL_SECRET not in str(settings)
    assert settings.alpaca_api_secret.get_secret_value() == SENTINEL_SECRET


def test_reddit_enabled_without_credentials_is_rejected() -> None:
    with pytest.raises(ValidationError, match="requires reddit_client_id"):
        make_settings(enable_reddit=True)


def test_reddit_enabled_with_credentials_is_accepted() -> None:
    settings = make_settings(
        enable_reddit=True,
        reddit_client_id="id",
        reddit_client_secret="shh",  # noqa: S106
    )

    assert settings.enable_reddit


def test_live_mode_requires_disabling_paper_flag() -> None:
    with pytest.raises(ValidationError, match="requires alpaca_paper=False"):
        make_settings(trading_mode=TradingMode.LIVE)


def test_live_mode_requires_explicit_risk_acknowledgement() -> None:
    with pytest.raises(ValidationError, match="acknowledge_live_trading_risk"):
        make_settings(trading_mode=TradingMode.LIVE, alpaca_paper=False)


def test_live_mode_accepted_when_fully_acknowledged() -> None:
    settings = make_settings(
        trading_mode=TradingMode.LIVE,
        alpaca_paper=False,
        acknowledge_live_trading_risk=True,
    )

    assert settings.executes_orders


def test_paper_mode_executes_orders() -> None:
    assert make_settings(trading_mode=TradingMode.PAPER).executes_orders


def test_empty_symbols_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least one entry"):
        make_settings(symbols=())


def test_unknown_setting_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(totally_unknown="x")


def test_get_settings_reads_environment_and_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_API_SECRET", SENTINEL_SECRET)

    assert get_settings() is get_settings()
