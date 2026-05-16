# scrapers/rss.py
# Fetches articles from free, public RSS feeds.
# No authentication required.

import re
import calendar
from datetime import datetime, timezone, timedelta

import feedparser
import requests
from bs4 import BeautifulSoup

from config import FREE_RSS_SOURCES, MAX_ARTICLES_PER_SOURCE, MAX_CONTENT_CHARS

LOOKBACK_HOURS = 24

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CKPM-Aggregator/1.0)",
}

# Strip characters that are invalid in XML 1.0
# Valid: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
_INVALID_XML = re.compile(
    r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]"
)

def sanitize_xml(raw: bytes) -> bytes:
    """Remove characters that are invalid in XML 1.0 before parsing."""
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        text = raw.decode("latin-1", errors="replace")
    cleaned = _INVALID_XML.sub("", text)
    return cleaned.encode("utf-8")


def fetch_feed(url: str):
    """
    Fetch and parse an RSS feed robustly.
    Falls back to feedparser direct fetch if requests fails.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        clean = sanitize_xml(resp.content)
        feed = feedparser.parse(clean)
        # If sanitized parse yielded entries, use it
        if feed.entries:
            return feed
    except Exception:
        pass
    # Fallback: let feedparser fetch directly (handles redirects etc.)
    return feedparser.parse(url)


def strip_html(html: str) -> str:
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def entry_published_utc(entry) -> datetime | None:
    parsed = getattr(entry, "published_parsed", None)
    if parsed is None:
        parsed = getattr(entry, "updated_parsed", None)
    if parsed is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)


def is_recent(entry, cutoff: datetime) -> bool:
    pub = entry_published_utc(entry)
    if pub is None:
        return True  # include if date unparseable
    return pub >= cutoff


def parse_entry(entry, source_name: str) -> dict | None:
    content_html = ""
    if hasattr(entry, "content") and entry.content:
        content_html = entry.content[0].get("value", "")
    if not content_html:
        content_html = getattr(entry, "summary", "")

    content_text = strip_html(content_html)[:MAX_CONTENT_CHARS]
    if not content_text:
        return None

    pub = entry_published_utc(entry)

    return {
        "source": source_name,
        "title": getattr(entry, "title", "Untitled"),
        "url": getattr(entry, "link", ""),
        "published": pub.isoformat() if pub else getattr(entry, "published", ""),
        "content": content_text,
        "summarized": False,
        "bullets": [],
        "themes": [],
    }


def fetch_rss_articles() -> list[dict]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    print(f"[rss] Fetching articles published after {cutoff.strftime('%Y-%m-%d %H:%M UTC')}")

    all_articles = []

    for source in FREE_RSS_SOURCES:
        name = source["name"]
        url = source["url"]
        print(f"  Fetching: {name}")

        try:
            feed = fetch_feed(url)

            if not feed.entries:
                bozo_msg = str(getattr(feed, "bozo_exception", "no entries"))
                print(f"    ⚠ No entries for {name}: {bozo_msg}")
                continue

            recent = [e for e in feed.entries[:MAX_ARTICLES_PER_SOURCE] if is_recent(e, cutoff)]

            for entry in recent:
                article = parse_entry(entry, name)
                if article:
                    all_articles.append(article)

            print(f"    ✓ {len(recent)} articles in last {LOOKBACK_HOURS}h")

        except Exception as e:
            print(f"    ✗ Error fetching {name}: {e}")

    return all_articles
