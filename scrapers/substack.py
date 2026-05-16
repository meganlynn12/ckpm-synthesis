# scrapers/substack.py
# Logs into Substack via Playwright, saves session, then fetches
# each publication's RSS feed using authenticated cookies.
# Sessions are cached to disk so we only re-login when they expire.

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from config import SUBSTACK_SOURCES, MAX_ARTICLES_PER_SOURCE, MAX_CONTENT_CHARS

SESSION_FILE = Path("sessions/substack_session.json")
SESSION_FILE.parent.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

async def login_substack() -> None:
    """Log into Substack and save session state to disk."""
    email = os.environ["SUBSTACK_EMAIL"]
    password = os.environ["SUBSTACK_PASSWORD"]

    print("  Logging into Substack...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        await page.goto("https://substack.com/sign-in", wait_until="networkidle")

        # Enter email
        await page.fill('input[type="email"]', email)
        await page.click('button:has-text("Continue")')
        await page.wait_for_timeout(1500)

        # Enter password (Substack uses a two-step flow)
        try:
            await page.fill('input[type="password"]', password)
            await page.click('button[type="submit"]')
            await page.wait_for_url("**/reader**", timeout=15000)
        except PlaywrightTimeoutError:
            # Some accounts land on a different post-login URL
            await page.wait_for_timeout(3000)
            if "substack.com" not in page.url:
                raise RuntimeError(f"Unexpected post-login URL: {page.url}")

        await context.storage_state(path=str(SESSION_FILE))
        print(f"  Session saved to {SESSION_FILE}")
        await browser.close()


def session_is_valid() -> bool:
    """Return True if a saved session file exists and is less than 7 days old."""
    if not SESSION_FILE.exists():
        return False
    mtime = datetime.fromtimestamp(SESSION_FILE.stat().st_mtime, tz=timezone.utc)
    age_days = (datetime.now(tz=timezone.utc) - mtime).days
    return age_days < 7


# ---------------------------------------------------------------------------
# Feed fetching
# ---------------------------------------------------------------------------

def strip_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


async def fetch_feed_with_session(url: str, cookies: dict) -> feedparser.FeedParserDict:
    """Fetch an RSS feed URL using saved session cookies via httpx."""
    async with httpx.AsyncClient(
        cookies=cookies,
        follow_redirects=True,
        timeout=20.0,
        headers={"User-Agent": "Mozilla/5.0 (compatible; personal-feed-reader/1.0)"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return feedparser.parse(response.text)


def parse_entry(entry: dict, source_name: str) -> dict | None:
    """Extract a normalised article dict from a feedparser entry."""
    # Get content — prefer full "content" field over summary
    content_html = ""
    if hasattr(entry, "content") and entry.content:
        content_html = entry.content[0].get("value", "")
    if not content_html:
        content_html = getattr(entry, "summary", "")

    content_text = strip_html(content_html)[:MAX_CONTENT_CHARS]
    if not content_text:
        return None  # Skip empty entries

    return {
        "source": source_name,
        "title": getattr(entry, "title", "Untitled"),
        "url": getattr(entry, "link", ""),
        "published": getattr(entry, "published", ""),
        "content": content_text,
        "summarized": False,   # Will be filled by summarizer.py
        "bullets": [],
        "themes": [],
    }


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

async def fetch_substack_articles() -> list[dict]:
    """
    Fetch recent articles from all Substack sources.
    Logs in if no valid session exists.
    Returns a flat list of article dicts.
    """
    if not session_is_valid():
        await login_substack()

    session_data = json.loads(SESSION_FILE.read_text())
    cookies = {c["name"]: c["value"] for c in session_data.get("cookies", [])}

    all_articles = []

    for source in SUBSTACK_SOURCES:
        slug = source["slug"]
        name = source["name"]
        feed_url = f"https://{slug}.substack.com/feed"
        print(f"  Fetching: {name} ({feed_url})")

        try:
            feed = await fetch_feed_with_session(feed_url, cookies)

            if feed.bozo and not feed.entries:
                print(f"    ⚠ Feed parse error for {name}: {feed.bozo_exception}")
                continue

            entries = feed.entries[:MAX_ARTICLES_PER_SOURCE]
            for entry in entries:
                article = parse_entry(entry, name)
                if article:
                    all_articles.append(article)

            print(f"    ✓ {len(entries)} articles")

        except httpx.HTTPStatusError as e:
            print(f"    ✗ HTTP {e.response.status_code} for {name}")
        except Exception as e:
            print(f"    ✗ Error fetching {name}: {e}")

        await asyncio.sleep(0.5)  # Be polite between requests

    return all_articles
