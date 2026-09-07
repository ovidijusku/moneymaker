"""Ingestion pipeline: scheduled jobs that keep the database current."""

from moneymaker.pipeline.advice import poll_advice
from moneymaker.pipeline.jobs import poll_bars, poll_news, poll_social
from moneymaker.pipeline.portfolio import poll_portfolio
from moneymaker.pipeline.scheduler import build_scheduler, run

__all__ = [
    "build_scheduler",
    "poll_advice",
    "poll_bars",
    "poll_news",
    "poll_portfolio",
    "poll_social",
    "run",
]
