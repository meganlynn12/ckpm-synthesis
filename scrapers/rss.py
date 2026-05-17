# scrapers/rss.py
# Fetches articles from free, public RSS feeds.
# No authentication required.

import re
import calendar
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import feedparser
import requests
from bs4 import BeautifulSoup

from config import FREE_RSS_SOURCES, MAX_ARTICLES_PER_SOURCE, MAX_CONTENT_CHARS

LOOKBACK_HOURS = 24

HEADERS = {
    # "User-Agent": "Mozilla/5.0 (compatible; CKPM-Aggregator/1.0)",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def strip_html(html: str) -> str:
    text = BeautifulSoup(html, "lxml").get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def parse_date(date_str: str) -> datetime | None:
    """Parse RSS date strings robustly."""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str).astimezone(timezone.utc)
    except Exception:
        pass
    try:
        from dateutil import parser as dateparser
        return dateparser.parse(date_str).astimezone(timezone.utc)
    except Exception:
        return None


def is_recent(pub: datetime | None, cutoff: datetime) -> bool:
    if pub is None:
        return True  # include if date unparseable
    return pub >= cutoff


def parse_bs4_feed(content: bytes) -> list[dict]:
    """
    Parse RSS/Atom feed using BeautifulSoup + lxml XML parser.
    lxml's XML parser has recovery mode enabled — handles malformed XML
    that feedparser's strict parser rejects.
    """
    soup = BeautifulSoup(content, "xml")  # uses lxml's lenient XML parser
    items = soup.find_all("item") or soup.find_all("entry")
    results = []
    for item in items:
        title = item.find("title")
        link = item.find("link")
        pub_date = item.find("pubDate") or item.find("published") or item.find("updated")
        content_tag = (
            item.find("content:encoded")
            or item.find("encoded")
            or item.find("content")
            or item.find("summary")
            or item.find("description")
        )

        link_url = ""
        if link:
            link_url = link.get("href") or link.get_text(strip=True)

        results.append({
            "title": title.get_text(strip=True) if title else "Untitled",
            "url": link_url,
            "published_str": pub_date.get_text(strip=True) if pub_date else "",
            "content_html": content_tag.get_text(separator=" ") if content_tag else "",
        })
    return results


def fetch_rss_articles() -> list[dict]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    print(f"[rss] Fetching articles published after {cutoff.strftime('%Y-%m-%d %H:%M UTC')}")

    all_articles = []

    for source in FREE_RSS_SOURCES:
        name = source["name"]
        url = source["url"]
        print(f"  Fetching: {name}")

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            raw = resp.content

            # Try feedparser first (fastest, most complete)
            feed = feedparser.parse(raw)
            used_bs4 = False

            if not feed.entries:
                # Feedparser failed — fall back to BeautifulSoup + lxml
                bs4_items = parse_bs4_feed(raw)
                if bs4_items:
                    used_bs4 = True
                    count = 0
                    for item in bs4_items[:MAX_ARTICLES_PER_SOURCE]:
                        pub = parse_date(item["published_str"])
                        if not is_recent(pub, cutoff):
                            continue
                        content_text = strip_html(item["content_html"])[:MAX_CONTENT_CHARS]
                        if not content_text:
                            continue
                        all_articles.append({
                            "source": name,
                            "title": item["title"],
                            "url": item["url"],
                            "published": pub.isoformat() if pub else item["published_str"],
                            "content": content_text,
                            "summarized": False,
                            "bullets": [],
                            "themes": [],
                        })
                        count += 1
                    print(f"    ✓ {count} articles in last {LOOKBACK_HOURS}h (via fallback parser)")
                else:
                    print(f"    ⚠ No entries for {name} (both parsers failed)")
                continue

            # feedparser succeeded — process normally
            count = 0
            for entry in feed.entries[:MAX_ARTICLES_PER_SOURCE]:
                parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
                pub = datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc) if parsed else None

                if not is_recent(pub, cutoff):
                    continue

                content_html = ""
                if hasattr(entry, "content") and entry.content:
                    content_html = entry.content[0].get("value", "")
                if not content_html:
                    content_html = getattr(entry, "summary", "")

                content_text = strip_html(content_html)[:MAX_CONTENT_CHARS]
                if not content_text:
                    continue

                all_articles.append({
                    "source": name,
                    "title": getattr(entry, "title", "Untitled"),
                    "url": getattr(entry, "link", ""),
                    "published": pub.isoformat() if pub else getattr(entry, "published", ""),
                    "content": content_text,
                    "summarized": False,
                    "bullets": [],
                    "themes": [],
                })
                count += 1

            print(f"    ✓ {count} articles in last {LOOKBACK_HOURS}h")

        except Exception as e:
            print(f"    ✗ Error fetching {name}: {e}")

    return all_articles