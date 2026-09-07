"""Account snapshot job.

The worker owns every outbound call, so the API can stay a pure reader of the
database. A stale snapshot degrades sizing accuracy; a failed one must not stop
the scheduler, so failures are logged and swallowed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from moneymaker.domain import Portfolio
from moneymaker.ingest.alpaca_account import TradingAccount, fetch_portfolio
from moneymaker.persistence import store_portfolio
from moneymaker.pipeline.jobs import SessionFactory

log = structlog.get_logger(__name__)


async def poll_portfolio(
    factory: SessionFactory,
    client: TradingAccount,
    *,
    now: datetime | None = None,
) -> Portfolio | None:
    try:
        portfolio = await fetch_portfolio(client, now=now or datetime.now(tz=UTC))
    except Exception as exc:  # a broker outage must not stop the scheduler
        log.warning("portfolio_fetch_failed", error=str(exc))
        return None

    async with factory() as session, session.begin():
        await store_portfolio(session, portfolio)

    log.info(
        "portfolio_stored",
        equity=str(portfolio.equity),
        cash=str(portfolio.cash),
        positions=len(portfolio.positions),
    )
    return portfolio
