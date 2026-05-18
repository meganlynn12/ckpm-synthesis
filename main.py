"""
main.py — CKPM Content Aggregator pipeline

1. Fetch articles from all RSS sources
2. Fetch Substack newsletters from Gmail
3. Deduplicate
4. Generate themed executive briefing via summarizer.py
5. Write output/content.json
"""

import json
import os
from datetime import datetime, timezone

from scrapers.rss import fetch_rss_articles
from scrapers.gmail import fetch_gmail_articles
from summarizer import generate_briefing

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "output", "content.json")
MAX_ARTICLES = 60


def main():
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    generated_at = datetime.now(timezone.utc).isoformat()

    print(f"\n{'='*60}")
    print(f"CKPM Content Aggregator — {run_date}")
    print(f"{'='*60}\n")

    # --- Fetch RSS ---
    print("[main] Fetching RSS sources...")
    rss_articles = fetch_rss_articles()
    print(f"[main] RSS: {len(rss_articles)} articles\n")

    # --- Fetch Gmail (Substack newsletters) ---
    print("[main] Fetching Substack newsletters from Gmail...")
    gmail_articles = fetch_gmail_articles()
    print(f"[main] Gmail: {len(gmail_articles)} articles\n")

    all_articles = rss_articles + gmail_articles
    print(f"[main] Total fetched: {len(all_articles)} raw articles")

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

    if len(unique_articles) > MAX_ARTICLES:
        print(f"[main] Capping to {MAX_ARTICLES} most recent articles")
        unique_articles = unique_articles[:MAX_ARTICLES]

    # --- Generate briefing ---
    briefing = generate_briefing(unique_articles, run_date)

    # --- Attach metadata ---
    briefing["generated_at"] = generated_at

    # --- Write output ---
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(briefing, f, indent=2, ensure_ascii=False)

    print(f"\n[main] Written to {OUTPUT_PATH}")
    print(f"[main] Generated at: {generated_at}")
    print(f"[main] Themes: {[t['theme'] for t in briefing.get('themes', [])]}")
    print(f"[main] Articles processed: {briefing.get('articles_processed', 0)}")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()