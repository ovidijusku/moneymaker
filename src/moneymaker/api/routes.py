"""API routes. Everything is a read of what the pipeline already decided."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from moneymaker.analysis.indicators import compute_indicators
from moneymaker.api.dependencies import SessionDep, SettingsDep
from moneymaker.api.stream import StreamEvent, build_stream
from moneymaker.domain import Advice, Bar, NewsEvent, Portfolio
from moneymaker.persistence import (
    latest_portfolio,
    load_advice,
    load_bars,
    load_news,
    load_posts,
)
from moneymaker.strategy.plan import TradePlan, build_plan
from moneymaker.universe import ASSETS, Asset

router = APIRouter(prefix="/api")

MAX_LOOKBACK_HOURS = 24 * 30
#: Enough bars to warm up every indicator with room to spare.
_PLAN_HISTORY_HOURS = 24


class Health(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"


class Config(BaseModel):
    """Safe-to-publish settings. Credentials are never exposed here."""

    model_config = ConfigDict(frozen=True)

    trading_mode: str
    symbols: tuple[str, ...]
    executes_orders: bool
    advice_poll_seconds: int
    assets: tuple[Asset, ...]
    #: Alpaca lists zero shortable crypto pairs, so the UI must never offer one.
    shorting_available: bool = False


def _since(hours: int) -> datetime:
    return datetime.now(tz=UTC) - timedelta(hours=hours)


@router.get("/health")
async def health() -> Health:
    return Health()


@router.get("/config")
async def config(settings: SettingsDep) -> Config:
    configured = set(settings.symbols)
    return Config(
        trading_mode=settings.trading_mode.value,
        symbols=settings.symbols,
        executes_orders=settings.executes_orders,
        advice_poll_seconds=settings.advice_poll_seconds,
        assets=tuple(asset for asset in ASSETS if asset.symbol in configured),
    )


@router.get("/advice")
async def advice(
    session: SessionDep,
    symbol: Annotated[str | None, Query(max_length=32)] = None,
    hours: Annotated[int, Query(ge=1, le=MAX_LOOKBACK_HOURS)] = 24,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[Advice]:
    journal = await load_advice(session, symbol=symbol, since=_since(hours))
    return list(journal[-limit:])


@router.get("/advice/latest")
async def latest_advice(session: SessionDep, settings: SettingsDep) -> list[Advice]:
    """The current opinion per configured symbol, newest first."""
    journal = await load_advice(session, since=_since(MAX_LOOKBACK_HOURS))
    newest: dict[str, Advice] = {}
    for item in journal:
        newest[item.symbol] = item
    return [newest[symbol] for symbol in settings.symbols if symbol in newest]


@router.get("/bars")
async def bars(
    session: SessionDep,
    symbol: Annotated[str, Query(max_length=32)],
    hours: Annotated[int, Query(ge=1, le=MAX_LOOKBACK_HOURS)] = 24,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> list[Bar]:
    window = await load_bars(session, symbol, since=_since(hours))
    return list(window[-limit:])


@router.get("/news")
async def news(
    session: SessionDep,
    symbol: Annotated[str | None, Query(max_length=32)] = None,
    hours: Annotated[int, Query(ge=1, le=MAX_LOOKBACK_HOURS)] = 24,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[NewsEvent]:
    events = await load_news(session, since=_since(hours))
    if symbol is not None:
        events = tuple(event for event in events if symbol in event.symbols)
    return list(reversed(events[-limit:]))


@router.get("/events")
async def events(
    session: SessionDep,
    symbol: Annotated[str | None, Query(max_length=32)] = None,
    hours: Annotated[int, Query(ge=1, le=MAX_LOOKBACK_HOURS)] = 24,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[StreamEvent]:
    """The landing feed: news, social chatter and advice merged, newest first."""
    since = _since(hours)
    return build_stream(
        news=await load_news(session, since=since),
        posts=await load_posts(session, since=since),
        advice=await load_advice(session, symbol=symbol, since=since),
        symbols=frozenset({symbol}) if symbol else None,
        limit=limit,
    )


@router.get("/portfolio")
async def portfolio(session: SessionDep) -> Portfolio | None:
    """None until the worker has taken its first account snapshot."""
    return await latest_portfolio(session)


@router.get("/plan")
async def plan(
    session: SessionDep,
    settings: SettingsDep,
    symbol: Annotated[str, Query(max_length=32)],
) -> TradePlan:
    """Sizing and stops for the newest advice on a symbol, against what we hold."""
    normalised = symbol.strip().upper()
    journal = await load_advice(session, symbol=normalised, since=_since(MAX_LOOKBACK_HOURS))
    if not journal:
        raise HTTPException(status_code=404, detail=f"no advice recorded for {normalised}")

    window = await load_bars(session, normalised, since=_since(_PLAN_HISTORY_HOURS))
    snapshot = compute_indicators(window)
    if snapshot is None:
        raise HTTPException(status_code=409, detail=f"not enough price history for {normalised}")

    account = await latest_portfolio(session)
    if account is None:
        raise HTTPException(status_code=409, detail="no account snapshot yet")

    return build_plan(
        advice=journal[-1],
        snapshot=snapshot,
        portfolio=account,
        config=settings.risk_config,
    )
