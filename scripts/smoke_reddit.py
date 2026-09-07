"""Read-only Reddit smoke test.

Pulls a handful of new submissions per configured subreddit and reports how many
were tagged with a symbol. Writes nothing and places no orders.

Run with: uv run python scripts/smoke_reddit.py
"""

from __future__ import annotations

import asyncio

from moneymaker.clients import create_reddit
from moneymaker.config import get_settings
from moneymaker.ingest.reddit import fetch_subreddit


async def main() -> int:
    settings = get_settings()
    reddit = create_reddit(settings)
    if reddit is None:
        print("reddit disabled or credentials missing; set ENABLE_REDDIT=true")
        return 1

    for subreddit in settings.reddit_subreddits:
        posts = await fetch_subreddit(
            reddit,
            subreddit,
            limit=min(settings.reddit_post_limit, 10),
            author_weights=settings.reddit_author_weights,
            universe=settings.symbols,
        )
        tagged = [post for post in posts if post.symbols]
        print(f"r/{subreddit}: {len(posts)} posts, {len(tagged)} symbol-tagged")
        for post in tagged[:3]:
            symbols = ",".join(sorted(post.symbols))
            print(f"  [{symbols}] {post.body.splitlines()[0][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
