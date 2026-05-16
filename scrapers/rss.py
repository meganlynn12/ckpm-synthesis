# scrapers/rss.py
# Fetches articles from free, public RSS feeds.
# No authentication required.

import re
import calendar
from datetime import datetime, timezone, timedelta

import feedparser
from bs4 import BeautifulSoup

from config import FREE_RSS_SOURCES, MAX_ARTICLES_PER_SOURCE, MAX_CONTENT_CHARS

# Only include articles published within this window
LOOKBACK_HOURS = 24


def strip_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def entry_published_utc(entry) -> datetime | None:
    """
    Return the entry's publish time as a UTC-aware datetime, or None if unparseable.
    feedparser provides published_parsed as a time.struct_time in UTC.
    """
    parsed = getattr(entry, "published_parsed", None)
    if parsed is None:
        parsed = getattr(entry, "updated_parsed", None)
    if parsed is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)


def is_recent(entry, cutoff: datetime) -> bool:
    """Return True if the entry was published after cutoff."""
    pub = entry_published_utc(entry)
    if pub is None:
        # If we can't parse the date, include it to avoid missing articles
        return True
    return pub >= cutoff


def parse_entry(entry, source_name: str) -> dict | None:
    """Extract a normalised article dict from a feedparser entry."""
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
    """
    Fetch articles published in the last LOOKBACK_HOURS from all free RSS sources.
    Returns a flat list of article dicts.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    print(f"[rss] Fetching articles published after {cutoff.strftime('%Y-%m-%d %H:%M UTC')}")

    all_articles = []

    for source in FREE_RSS_SOURCES:
        name = source["name"]
        url = source["url"]
        print(f"  Fetching: {name}")

        try:
            feed = feedparser.parse(url)

            if feed.bozo and not feed.entries:
                print(f"    ⚠ Feed parse error for {name}: {feed.bozo_exception}")
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