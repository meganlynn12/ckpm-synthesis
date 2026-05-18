"""
main_premium.py — Premium Journalism Content Aggregator pipeline

Pipeline:
1. Fetch newsletter emails from Gmail (scrapers/premium_gmail.py)
   Each article tagged: tier = "newsletter" | "breaking" | "longform"
2. Deduplicate
3. Route to three-tier summarizer (summarizer_premium.py):
   - Tier 1  newsletter  → structure extraction only (NYT, Economist)
   - Tier 2  breaking    → end-of-day narrative digest (NYT alerts)
   - Tier 3  longform    → deep synthesis (Foreign Affairs, Atlantic, MIT TR)
4. Write output/premium_content.json  (current)
5. Write output/premium_YYYY-MM-DD-HH.json  (archive)
6. Update output/premium_archive.json  (index)
"""

import json
import os
from datetime import datetime, timezone

from scrapers.premium_gmail import fetch_premium_gmail_articles
from summarizer_premium import generate_premium_briefing

OUTPUT_DIR         = os.path.join(os.path.dirname(__file__), "output")
CURRENT_PATH       = os.path.join(OUTPUT_DIR, "premium_content.json")
ARCHIVE_INDEX_PATH = os.path.join(OUTPUT_DIR, "premium_archive.json")

RUN_LABELS = {
    10: "6 AM",  11: "6 AM",
    16: "12 PM", 17: "12 PM",
    22: "6 PM",  23: "6 PM",
}

MAX_ARTICLES = 80   # higher cap than substack pipeline — newsletters can be dense


def get_run_label(dt: datetime) -> str:
    return RUN_LABELS.get(dt.hour, f"{dt.strftime('%H:%M')} UTC")


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
    run_date         = now.strftime("%Y-%m-%d")
    run_label        = get_run_label(now)
    archive_filename = f"premium_{now.strftime('%Y-%m-%d-%H')}.json"
    archive_path     = os.path.join(OUTPUT_DIR, archive_filename)
    generated_at     = now.isoformat()

    print(f"\n{'='*60}")
    print(f"Premium Journalism Aggregator — {run_date} {run_label}")
    print(f"{'='*60}\n")

    # ── Fetch ──
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

    # ── Deduplicate ──
    seen, unique = set(), []
    for article in articles:
        key       = article.get("url") or article.get("title", "").lower().strip()
        title_key = article.get("title", "").lower().strip()
        if key not in seen and title_key not in seen:
            seen.add(key)
            seen.add(title_key)
            unique.append(article)

    print(f"[main_premium] {len(unique)} articles after deduplication")

    if len(unique) > MAX_ARTICLES:
        print(f"[main_premium] Capping to {MAX_ARTICLES}")
        unique = unique[:MAX_ARTICLES]

    # ── Three-tier synthesis ──
    briefing = generate_premium_briefing(unique, run_date)

    # ── Attach run metadata ──
    briefing["generated_at"]      = generated_at
    briefing["run_label"]         = run_label
    briefing["archive_filename"]  = archive_filename

    # ── Write current ──
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(CURRENT_PATH, "w", encoding="utf-8") as f:
        json.dump(briefing, f, indent=2, ensure_ascii=False)
    print(f"\n[main_premium] Written → premium_content.json")

    # ── Write archive ──
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(briefing, f, indent=2, ensure_ascii=False)
    print(f"[main_premium] Archived → {archive_filename}")

    # ── Update archive index ──
    counts = briefing.get("counts", {})
    update_archive_index({
        "date":             run_date,
        "run_label":        run_label,
        "generated_at":     generated_at,
        "filename":         archive_filename,
        "pipeline":         "premium",
        "counts":           counts,
        "total_articles":   sum(counts.values()),
    })
    print(f"[main_premium] Archive index updated")

    print(f"\n[main_premium] Summary:")
    print(f"  Newsletters  : {counts.get('newsletter', 0)}")
    print(f"  Breaking     : {counts.get('breaking', 0)}")
    print(f"  Longform     : {counts.get('longform', 0)}")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
