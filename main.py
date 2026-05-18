"""
main.py — CKPM Content Aggregator pipeline

1. Fetch articles from all RSS sources
2. Fetch Substack newsletters from Gmail
3. Deduplicate
4. Generate themed executive briefing via summarizer.py
5. Write output/content.json (current)
6. Write output/YYYY-MM-DD-HH.json (archive)
7. Update output/archive.json index
"""

import json
import os
from datetime import datetime, timezone

from scrapers.rss import fetch_rss_articles
from scrapers.gmail import fetch_gmail_articles
from summarizer import generate_briefing

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
CURRENT_PATH = os.path.join(OUTPUT_DIR, "content.json")
ARCHIVE_INDEX_PATH = os.path.join(OUTPUT_DIR, "archive.json")

# Human-readable run labels by UTC hour
RUN_LABELS = {
    10: "6 AM",
    11: "6 AM",   # DST fallback
    16: "12 PM",
    17: "12 PM",  # DST fallback
    22: "6 PM",
    23: "6 PM",   # DST fallback
}

MAX_ARTICLES = 60


def get_run_label(dt: datetime) -> str:
    """Return a human-readable label for this run based on UTC hour."""
    return RUN_LABELS.get(dt.hour, f"{dt.strftime('%H:%M')} UTC")


def update_archive_index(archive_entry: dict) -> None:
    """Add this run to the archive index, keeping most recent first."""
    index = []
    if os.path.exists(ARCHIVE_INDEX_PATH):
        try:
            with open(ARCHIVE_INDEX_PATH, "r") as f:
                index = json.load(f)
        except Exception:
            index = []

    # Avoid duplicates by filename
    index = [e for e in index if e.get("filename") != archive_entry["filename"]]
    index.insert(0, archive_entry)

    with open(ARCHIVE_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def main():
    now = datetime.now(timezone.utc)
    run_date = now.strftime("%Y-%m-%d")
    run_label = get_run_label(now)
    archive_filename = f"{now.strftime('%Y-%m-%d-%H')}.json"
    archive_path = os.path.join(OUTPUT_DIR, archive_filename)
    generated_at = now.isoformat()

    print(f"\n{'='*60}")
    print(f"CKPM Content Aggregator — {run_date} {run_label}")
    print(f"{'='*60}\n")

    # --- Fetch RSS ---
    print("[main] Fetching RSS sources...")
    rss_articles = fetch_rss_articles()
    print(f"[main] RSS: {len(rss_articles)} articles\n")

    # --- Fetch Gmail ---
    print("[main] Fetching Substack newsletters from Gmail...")
    gmail_articles = fetch_gmail_articles()
    print(f"[main] Gmail: {len(gmail_articles)} articles\n")

    all_articles = rss_articles + gmail_articles
    print(f"[main] Total fetched: {len(all_articles)} raw articles")

    # --- Deduplicate ---
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
    briefing["run_label"] = run_label
    briefing["archive_filename"] = archive_filename

    # --- Write current ---
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(CURRENT_PATH, "w", encoding="utf-8") as f:
        json.dump(briefing, f, indent=2, ensure_ascii=False)
    print(f"\n[main] Written to content.json")

    # --- Write archive file ---
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(briefing, f, indent=2, ensure_ascii=False)
    print(f"[main] Archived to {archive_filename}")

    # --- Update archive index ---
    archive_entry = {
        "date": run_date,
        "run_label": run_label,
        "generated_at": generated_at,
        "filename": archive_filename,
        "articles_processed": briefing.get("articles_processed", 0),
        "theme_count": len(briefing.get("themes", [])),
        "publications": briefing.get("publications", []),
    }
    update_archive_index(archive_entry)
    print(f"[main] Archive index updated")

    print(f"\n[main] Themes: {[t['theme'] for t in briefing.get('themes', [])]}")
    print(f"[main] Articles processed: {briefing.get('articles_processed', 0)}")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()