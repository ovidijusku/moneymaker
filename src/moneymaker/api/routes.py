"""API routes. Everything is a read of what the pipeline already decided."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from moneymaker.api.dependencies import SessionDep, SettingsDep
from moneymaker.domain import Advice, Bar, NewsEvent
from moneymaker.persistence import load_advice, load_bars, load_news

router = APIRouter(prefix="/api")

MAX_LOOKBACK_HOURS = 24 * 30


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


def _since(hours: int) -> datetime:
    return datetime.now(tz=UTC) - timedelta(hours=hours)


@router.get("/health")
async def health() -> Health:
    return Health()


@router.get("/config")
async def config(settings: SettingsDep) -> Config:
    return Config(
        trading_mode=settings.trading_mode.value,
        symbols=settings.symbols,
        executes_orders=settings.executes_orders,
        advice_poll_seconds=settings.advice_poll_seconds,
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
