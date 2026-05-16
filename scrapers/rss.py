# scrapers/rss.py
# Fetches articles from free, public RSS feeds.
# No authentication required.

import re
import feedparser
from bs4 import BeautifulSoup

from config import FREE_RSS_SOURCES, MAX_ARTICLES_PER_SOURCE, MAX_CONTENT_CHARS


def strip_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def parse_entry(entry: dict, source_name: str) -> dict | None:
    """Extract a normalised article dict from a feedparser entry."""
    content_html = ""
    if hasattr(entry, "content") and entry.content:
        content_html = entry.content[0].get("value", "")
    if not content_html:
        content_html = getattr(entry, "summary", "")

    content_text = strip_html(content_html)[:MAX_CONTENT_CHARS]
    if not content_text:
        return None

    return {
        "source": source_name,
        "title": getattr(entry, "title", "Untitled"),
        "url": getattr(entry, "link", ""),
        "published": getattr(entry, "published", ""),
        "content": content_text,
        "summarized": False,
        "bullets": [],
        "themes": [],
    }


def fetch_rss_articles() -> list[dict]:
    """
    Fetch recent articles from all free RSS sources.
    Returns a flat list of article dicts.
    """
    all_articles = []

    for source in FREE_RSS_SOURCES:
        name = source["name"]
        url = source["url"]
        print(f"  Fetching: {name} ({url})")

        try:
            feed = feedparser.parse(url)

            if feed.bozo and not feed.entries:
                print(f"    ⚠ Feed parse error for {name}: {feed.bozo_exception}")
                continue

            entries = feed.entries[:MAX_ARTICLES_PER_SOURCE]
            for entry in entries:
                article = parse_entry(entry, name)
                if article:
                    all_articles.append(article)

            print(f"    ✓ {len(entries)} articles")

        except Exception as e:
            print(f"    ✗ Error fetching {name}: {e}")

    return all_articles
