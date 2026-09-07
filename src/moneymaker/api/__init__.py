"""Read-only HTTP surface over the advisory journal.

Deliberately read-only: there is no execution engine behind this, so there is
nothing here that can move money.
"""

from __future__ import annotations

from moneymaker.api.app import create_app

__all__ = ["create_app"]
