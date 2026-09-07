"""Async engine and session wiring."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from moneymaker.persistence.schema import Base

_SQLITE_FILE_PREFIX = "sqlite+aiosqlite:///"


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    if url.startswith(_SQLITE_FILE_PREFIX):
        path = Path(url.removeprefix(_SQLITE_FILE_PREFIX))
        if path.name != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
    return create_async_engine(url, echo=echo)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_schema(engine: AsyncEngine) -> None:
    """Bootstrap for local dev; Alembic owns schema changes once deployed."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
