"""
config.py — Source definitions for CKPM Content Aggregator
"""

# ---------------------------------------------------------------------------
# Fetcher settings
# ---------------------------------------------------------------------------

MAX_ARTICLES_PER_SOURCE = 10
MAX_CONTENT_CHARS = 8000


# ---------------------------------------------------------------------------
# Active RSS sources — public feeds that work cleanly
# ---------------------------------------------------------------------------

FREE_RSS_SOURCES = [
    # {"name": "Silver Bulletin",  "url": "https://www.natesilver.net/feed"},
    {"name": "The Bulwark",      "url": "https://www.thebulwark.com/feed"},
    {"name": "Slow Boring",      "url": "https://www.slowboring.com/feed"},
    {"name": "Scott Galloway",   "url": "https://www.profgmedia.com/feed"},
    {"name": "John Ellis",       "url": "https://substack.news-items.com/feed"},
    {"name": "ProPublica",       "url": "https://www.propublica.org/feeds/propublica/main"},
    {"name": "SCOTUSblog",       "url": "https://www.scotusblog.com/feed/"},
    {"name": "Onest Network",    "url": "https://www.onestnetwork.com/rss/"},
]


# ---------------------------------------------------------------------------
# Substack newsletters — ingested via Gmail (any @substack.com sender)
# Listed here for documentation; gmail.py fetches all @substack.com emails
# ---------------------------------------------------------------------------

SUBSTACK_GMAIL_SOURCES = [
    "Nate Silver / Silver Bulletin",
    "Heather Cox Richardson",
    "Phillips P. O'Brien",
    "Paul Krugman",
    "Robert Reich",
    "Wake Up To Politics",
    "G. Elliott Morris",
    "Sabato's Crystal Ball",
]


# ---------------------------------------------------------------------------
# PENDING — Phase 2: Playwright scrapers
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

# ---------------------------------------------------------------------------
# ADDITIONS TO config.py
# Add this block below the existing PLAYWRIGHT_SOURCES section
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Premium Gmail newsletter sources
# These are ingested via scrapers/premium_gmail.py using the same Gmail OAuth
# token as the Substack pipeline. Each source maps to a specific newsletter
# sender domain and optional subject keywords.
# See scrapers/premium_gmail.py for full matching logic.
# ---------------------------------------------------------------------------

PREMIUM_GMAIL_SOURCES = [
    {
        "name": "New York Times",
        "sender_domain": "nytimes.com",
        "newsletters": ["The Morning", "DealBook", "Evening Briefing"],
    },
    {
        "name": "MIT Technology Review",
        "sender_domain": "technologyreview.com",
        "newsletters": ["The Download", "Weekend Reads"],
    },
    {
        "name": "The Atlantic",
        "sender_domain": "theatlantic.com",
        "newsletters": ["The Atlantic Daily"],
    },
    {
        "name": "Financial Times",
        "sender_domain": "ft.com",
        "newsletters": ["FirstFT", "FT Weekend"],
    },
    {
        "name": "The Economist",
        "sender_domain": "economist.com",
        "newsletters": ["Espresso", "Weekly edition"],
    },
    {
        "name": "Wall Street Journal",
        "sender_domain": "wsj.com",
        "newsletters": ["What's News", "The 10-Point"],
    },
    {
        "name": "Foreign Affairs",
        "sender_domain": "foreignaffairs.com",
        "newsletters": [],  # all newsletters
    },
]