"""
main.py — CKPM Content Aggregator pipeline

1. Fetch articles from all RSS sources
2. Deduplicate
3. Generate themed executive briefing via summarizer.py
4. Write output/content.json
"""

import json
import os
from datetime import datetime, timezone

from scrapers.rss import fetch_rss_articles
from summarizer import generate_briefing

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "output", "content.json")
MAX_ARTICLES = 60  # Cap to keep Phase 1 token cost reasonable


def main():
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"CKPM Content Aggregator — {run_date}")
    print(f"{'='*60}\n")

    # --- Fetch ---
    print("[main] Fetching RSS sources...")
    all_articles = fetch_rss_articles()
    print(f"[main] Fetched {len(all_articles)} raw articles")

    # --- Deduplicate by URL + title ---
    seen = set()
    unique_articles = []
    for article in all_articles:
        key = article.get("url") or article.get("title", "").lower().strip()
        title_key = article.get("title", "").lower().strip()
        if key not in seen and title_key not in seen:
            seen.add(key)
            seen.add(title_key)
            unique_articles.append(article)

    print(f"[main] {len(unique_articles)} articles after deduplication")

    # Cap total articles to keep costs bounded
    if len(unique_articles) > MAX_ARTICLES:
        print(f"[main] Capping to {MAX_ARTICLES} most recent articles")
        unique_articles = unique_articles[:MAX_ARTICLES]

    # --- Generate briefing ---
    briefing = generate_briefing(unique_articles, run_date)

    # --- Write output ---
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(briefing, f, indent=2, ensure_ascii=False)

    print(f"\n[main] Written to {OUTPUT_PATH}")
    print(f"[main] Themes: {[t['theme'] for t in briefing.get('themes', [])]}")
    print(f"[main] Articles processed: {briefing.get('articles_processed', 0)}")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()