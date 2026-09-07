"""Ingestion adapters. Each exposes a pure parser plus a thin I/O wrapper."""

from moneymaker.ingest.rss import fetch_feed, parse_entry, parse_feed
from moneymaker.ingest.symbols import extract_symbols

__all__ = ["extract_symbols", "fetch_feed", "parse_entry", "parse_feed"]
