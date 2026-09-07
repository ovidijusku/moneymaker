"""Entry point: ``python -m moneymaker``."""

from __future__ import annotations

import asyncio

from moneymaker.config import get_settings
from moneymaker.logging import configure_logging
from moneymaker.pipeline import run


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
