# config.py
# All source definitions for the content aggregator.
# Substack slugs are verified where possible — flagged with TODO where uncertain.

# ---------------------------------------------------------------------------
# Substack sources — fetched via authenticated Playwright session
# ---------------------------------------------------------------------------
SUBSTACK_SOURCES = [
    # Free Substacks (public RSS, but we use the same auth session for consistency)
    {"name": "Letters from an American",    "slug": "heathercoxrichardson"},
    {"name": "Phillips P. O'Brien",         "slug": "phillipspobrien"},
    {"name": "Paul Krugman",                "slug": "paulkrugman"},
    {"name": "Robert Reich",                "slug": "robertreich"},
    {"name": "Ruth Ben-Ghiat",              "slug": "ruthbenghiat"},
    {"name": "Wake Up To Politics",         "slug": "wakeuptopolitics"},       # Gabe Fleisher
    {"name": "Slow Boring",                 "slug": "slowboring"},              # Matthew Yglesias
    {"name": "G. Elliott Morris",           "slug": "gelliottmorris"},
    {"name": "John Ellis News Items",       "slug": "johnjellispassages"},      # TODO: verify slug
    {"name": "No Mercy / No Malice",        "slug": "profgalloway"},            # TODO: verify — may be profgalloway.com not Substack
    {"name": "Sabato's Crystal Ball", "slug": "sabatoscrystalball"},

    # Paid Substacks
    {"name": "Silver Bulletin",             "slug": "natesilver"},              # Nate Silver
    {"name": "The Bulwark",                 "slug": "thebulwark"},              # TODO: verify slug
]

# ---------------------------------------------------------------------------
# Free RSS sources
# ---------------------------------------------------------------------------
FREE_RSS_SOURCES = [
    {
        "name": "NPR News",
        "url": "https://feeds.npr.org/1001/rss.xml",
    },
    {
        "name": "ProPublica",
        "url": "https://feeds.propublica.org/propublica/main",
    },
    {
        "name": "SCOTUSblog",
        "url": "https://www.scotusblog.com/feed/",
    },
    {
        "name": "Onest Network",
        "url": "https://www.onestnetwork.com/feed/",                            # TODO: verify — may differ
    },
]

# ---------------------------------------------------------------------------
# Fetch settings
# ---------------------------------------------------------------------------
MAX_ARTICLES_PER_SOURCE = 5     # How many recent articles to pull per source
MAX_CONTENT_CHARS = 8000        # Truncate article content before sending to Claude
                                # (keeps token costs reasonable)
