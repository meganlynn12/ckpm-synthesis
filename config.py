"""
config.py — RSS source definitions for CKPM Content Aggregator

All sources in FREE_RSS_SOURCES are publicly accessible without auth.
Substack public feeds return full article content in content:encoded.

PENDING sources (Playwright) are defined but not yet wired in.
"""

# ---------------------------------------------------------------------------
# Fetcher settings
# ---------------------------------------------------------------------------

MAX_ARTICLES_PER_SOURCE = 10   # max articles pulled per RSS feed per run
MAX_CONTENT_CHARS = 8000       # truncate article content before passing to Claude


# ---------------------------------------------------------------------------
# Active RSS sources — fetched every run
# ---------------------------------------------------------------------------

FREE_RSS_SOURCES = [

    # --- Verified: full content in feed ---
    {"name": "Silver Bulletin",     "url": "https://www.natesilver.net/feed"},
    {"name": "The Bulwark",         "url": "https://www.thebulwark.com/feed"},

    # --- Substack (public RSS, full content) ---
    {"name": "Heather Cox Richardson",  "url": "https://heathercoxrichardson.substack.com/feed"},
    {"name": "Phillips P. O'Brien",     "url": "https://phillipspobrien.substack.com/feed"},
    {"name": "Paul Krugman",            "url": "https://paulkrugman.substack.com/feed"},
    {"name": "Robert Reich",            "url": "https://robertreich.substack.com/feed"},
    # {"name": "Ruth Ben-Ghiat",          "url": "https://ruthbenghiat.substack.com/feed"},
    {"name": "Wake Up To Politics",     "url": "https://wakeuptopolitics.substack.com/feed"},
    {"name": "Slow Boring",             "url": "https://www.slowboring.com/feed"},
    {"name": "G. Elliott Morris",       "url": "https://gelliottmorris.substack.com/feed"},
    {"name": "John Ellis",              "url": "https://substack.news-items.com/feed"},
    {"name": "Scott Galloway",          "url": "https://www.profgmedia.com/feed"},
    # {"name": "Prof G Media (Monday Rage)", "url": "https://www.profgmedia.com/s/monday-rage/feed"},
    # {"name": "Sabato's Crystal Ball",   "url": "https://crystalball.substack.com/feed"},

    # --- Free news RSS ---
    # {"name": "NPR",        "url": "https://feeds.npr.org/1001/rss.xml"},
    {"name": "ProPublica", "url": "https://www.propublica.org/feeds/propublica/main"},
    {"name": "SCOTUSblog", "url": "https://www.scotusblog.com/feed/"},
]


# ---------------------------------------------------------------------------
# PENDING — Phase 2: Playwright scrapers
# Paywalled sites requiring login or JS rendering
# ---------------------------------------------------------------------------

PLAYWRIGHT_SOURCES = [
    {"name": "New York Times",        "url": "https://www.nytimes.com"},
    {"name": "The Atlantic",          "url": "https://www.theatlantic.com"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com"},
    {"name": "Wall Street Journal",   "url": "https://www.wsj.com"},
    {"name": "The Economist",         "url": "https://www.economist.com"},
    {"name": "Financial Times",       "url": "https://www.ft.com"},
    {"name": "Foreign Affairs",       "url": "https://www.foreignaffairs.com"},
]