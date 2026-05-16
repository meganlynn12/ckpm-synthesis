# main.py
# Orchestrates the full Phase 1 pipeline:
#   1. Fetch Substack articles (via Playwright session)
#   2. Fetch free RSS articles
#   3. Summarize all articles with Claude
#   4. Generate daily digest
#   5. Write output/content.json

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from scrapers.substack import fetch_substack_articles
from scrapers.rss import fetch_rss_articles
from summarizer import summarize_articles

OUTPUT_FILE = Path("output/content.json")
OUTPUT_FILE.parent.mkdir(exist_ok=True)


async def main() -> None:
    start = datetime.now(tz=timezone.utc)
    print(f"\n{'='*60}")
    print(f"Content Aggregator — {start.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    # ------------------------------------------------------------------ #
    # 1. Fetch
    # ------------------------------------------------------------------ #
    print("[ 1/3 ] Fetching Substack articles...")
    try:
        substack_articles = await fetch_substack_articles()
    except Exception as e:
        print(f"  ✗ Substack fetch failed: {e}")
        substack_articles = []

    print(f"\n[ 2/3 ] Fetching free RSS articles...")
    try:
        rss_articles = fetch_rss_articles()
    except Exception as e:
        print(f"  ✗ RSS fetch failed: {e}")
        rss_articles = []

    all_articles = substack_articles + rss_articles
    print(f"\n  Total articles fetched: {len(all_articles)}")

    if not all_articles:
        print("\n  No articles fetched — exiting.")
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # 2. Summarize
    # ------------------------------------------------------------------ #
    print(f"\n[ 3/3 ] Summarizing with Claude...")
    summarized_articles, digest = await summarize_articles(all_articles)

    # ------------------------------------------------------------------ #
    # 3. Write output
    # ------------------------------------------------------------------ #
    # Sort by relevance descending so the frontend can show top articles first
    summarized_articles.sort(key=lambda a: a.get("relevance", 0), reverse=True)

    # Strip raw content from output to keep file size reasonable
    for article in summarized_articles:
        article.pop("content", None)

    elapsed = (datetime.now(tz=timezone.utc) - start).total_seconds()

    output = {
        "generated_at": start.isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "article_count": len(summarized_articles),
        "digest": digest,
        "articles": summarized_articles,
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    print(f"\n{'='*60}")
    print(f"Done in {elapsed:.1f}s — {len(summarized_articles)} articles written to {OUTPUT_FILE}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
