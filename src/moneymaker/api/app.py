"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from moneymaker.api.routes import router
from moneymaker.config import Settings, get_settings
from moneymaker.persistence import create_engine, create_schema, create_session_factory

log = structlog.get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = create_engine(settings.database_url)
    await create_schema(engine)
    app.state.session_factory = create_session_factory(engine)
    try:
        yield
    finally:
        await engine.dispose()


async def _unhandled_error(request: Request, _exc: Exception) -> JSONResponse:
    """Log the detail, return none of it. Stack traces are not a public API."""
    log.exception("request_failed", path=request.url.path, method=request.method)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="moneymaker",
        version="0.1.0",
        summary="Advisory-only crypto signals. This API cannot place orders.",
        lifespan=_lifespan,
    )
    app.state.settings = settings or get_settings()
    app.add_exception_handler(Exception, _unhandled_error)
    app.include_router(router)
    return app
