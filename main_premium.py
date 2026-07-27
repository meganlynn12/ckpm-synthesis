"""
main_premium.py — Premium Journalism Content Aggregator pipeline (PROPINT)

1. Fetch newsletter emails from Gmail (3-tier: newsletter / breaking / longform)
2. Deduplicate (breaking news alerts are never deduplicated)
3. Synthesize via summarizer_premium.py (Gemini)
4. Write output/premium_content.json (current)
5. Write output/premium_YYYY-MM-DD-HHMM.json (archive) — always; manual runs labeled
6. Update output/premium_archive.json index
"""

import json
import os
from datetime import datetime, timezone

from scrapers.premium_gmail import fetch_premium_gmail_articles
from summarizer_premium import generate_premium_briefing

OUTPUT_DIR         = os.path.join(os.path.dirname(__file__), "output")
CURRENT_PATH       = os.path.join(OUTPUT_DIR, "premium_content.json")
ARCHIVE_INDEX_PATH = os.path.join(OUTPUT_DIR, "premium_archive.json")

MAX_ARTICLES = 80


def get_run_label(now: datetime, is_scheduled: bool) -> str:
    if is_scheduled:
        return "7 AM"
    return f"Manual {now.strftime('%Y-%m-%d %H:%M')} UTC"


def update_archive_index(entry: dict) -> None:
    index = []
    if os.path.exists(ARCHIVE_INDEX_PATH):
        try:
            with open(ARCHIVE_INDEX_PATH, "r") as f:
                index = json.load(f)
        except Exception:
            index = []
    index = [e for e in index if e.get("filename") != entry["filename"]]
    index.insert(0, entry)
    with open(ARCHIVE_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def main():
    now              = datetime.now(timezone.utc)
    is_scheduled     = os.environ.get("GITHUB_EVENT_NAME") == "schedule"
    run_date         = now.strftime("%Y-%m-%d")
    run_label        = get_run_label(now, is_scheduled)
    archive_filename = f"premium_{now.strftime('%Y-%m-%d-%H%M')}.json"
    archive_path     = os.path.join(OUTPUT_DIR, archive_filename)
    generated_at     = now.isoformat()

    print(f"\n{'='*60}")
    print(f"Premium Journalism Aggregator — {run_date} {run_label}")
    print(f"{'='*60}\n")

    print("[main_premium] Fetching premium journalism newsletters...")
    articles = fetch_premium_gmail_articles()
    print(f"[main_premium] Fetched: {len(articles)} articles\n")

    if not articles:
        print("[main_premium] No articles found. Writing empty output.")
        empty = {
            "date": run_date, "generated_at": generated_at,
            "run_label": run_label, "archive_filename": archive_filename,
            "pipeline": "premium", "executive_summary": "",
            "newsletters": [], "breaking_digest": None, "longform": [],
            "counts": {"newsletter": 0, "breaking": 0, "longform": 0},
        }
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(CURRENT_PATH, "w", encoding="utf-8") as f:
            json.dump(empty, f, indent=2, ensure_ascii=False)
        return

    # Breaking news alerts are never deduplicated — the summarizer needs the
    # full set of alerts to collapse into a coherent digest.
    seen, unique = set(), []
    for article in articles:
        if article.get("tier") == "breaking":
            unique.append(article)
            continue
        key       = article.get("url") or article.get("title", "").lower().strip()
        title_key = article.get("title", "").lower().strip()
        if key not in seen and title_key not in seen:
            seen.add(key)
            seen.add(title_key)
            unique.append(article)

    breaking_count = sum(1 for a in unique if a.get("tier") == "breaking")
    print(f"[main_premium] {len(unique)} articles after deduplication "
          f"({breaking_count} breaking alerts preserved)")

    if len(unique) > MAX_ARTICLES:
        breaking  = [a for a in unique if a.get("tier") == "breaking"]
        non_break = [a for a in unique if a.get("tier") != "breaking"]
        non_break = non_break[:MAX_ARTICLES - len(breaking)]
        unique    = breaking + non_break
        print(f"[main_premium] Capped to {len(unique)} (all {len(breaking)} breaking alerts kept)")

    briefing = generate_premium_briefing(unique, run_date)

    briefing["generated_at"]     = generated_at
    briefing["run_label"]        = run_label
    briefing["archive_filename"] = archive_filename

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(CURRENT_PATH, "w", encoding="utf-8") as f:
        json.dump(briefing, f, indent=2, ensure_ascii=False)
    print(f"\n[main_premium] Written → premium_content.json")

    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(briefing, f, indent=2, ensure_ascii=False)
    print(f"[main_premium] Archived → {archive_filename}")

    counts = briefing.get("counts", {})
    update_archive_index({
        "date":           run_date,
        "run_label":      run_label,
        "generated_at":   generated_at,
        "filename":       archive_filename,
        "pipeline":       "premium",
        "counts":         counts,
        "total_articles": sum(counts.values()),
        "manual":         not is_scheduled,
    })
    print(f"[main_premium] Archive index updated")

    print(f"\n[main_premium] Summary:")
    print(f"  Newsletters  : {counts.get('newsletter', 0)}")
    print(f"  Breaking     : {counts.get('breaking', 0)}")
    print(f"  Longform     : {counts.get('longform', 0)}")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()