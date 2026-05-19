"""
scrapers/premium_gmail.py

Gmail ingestion for premium journalism sources across two accounts.

Account 1 (GMAIL_TOKEN_JSON)     — authorized Gmail (Substack pipeline)
Account 2 (GMAIL_TOKEN_JSON_2)   — second Gmail
                                   MIT TR, NYT, Economist, Atlantic, Foreign Affairs

Tier detection (dynamic, per email):
  breakingnews@nytimes.com              → always "breaking"
  nytdirect@nytimes.com + "french"      → "longform" (David French column)
  email@theatlantic.com + known subject → "newsletter" (Atlantic Daily etc.)
  email@theatlantic.com + other         → "longform" (feature articles)
  everything else                       → "newsletter"

Lookback windows:
  newsletter : 13h both runs
  breaking   : 18h PM run only (skipped on AM run)
  longform   : 72h both runs (weekly columns need longer window)

AM run (UTC 10-11): newsletter + longform only, breaking skipped
PM run (UTC 22-23): newsletter + longform + breaking
"""

import base64
import json
import os
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ---------------------------------------------------------------------------
# Run-time detection
# ---------------------------------------------------------------------------

PM_HOURS = {22, 23}

def _is_pm_run() -> bool:
    return datetime.now(timezone.utc).hour in PM_HOURS

# ---------------------------------------------------------------------------
# Tier-specific config
# ---------------------------------------------------------------------------

LOOKBACK_HOURS_BY_TIER = {
    "newsletter": 13,
    "breaking":   18,
    "longform":   72,
}

MAX_PER_SENDER_BY_TIER = {
    "newsletter": 5,
    "breaking":   20,
    "longform":   5,
}

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# ---------------------------------------------------------------------------
# Promotional email filtering
# ---------------------------------------------------------------------------

PROMO_QUERY_EXCLUSIONS = (
    # "-category:promotions"
    " -subject:subscribe"
    " -subject:subscription"
    " -subject:renew"
    " -subject:renewal"
    " -subject:gift"
    " -subject:offer"
    " -subject:deal"
    " -subject:save"
    " -subject:payment"
    " -subject:invoice"
)

PROMO_SUBJECT_KEYWORDS = [
    "subscribe", "subscription", "renew", "renewal",
    "gift", "offer", "deal", "save ", "% off",
    "free trial", "your account", "payment", "invoice",
    "last chance", "limited time", "act now", "upgrade",
    "billing", "expires", "expiring",
]

# ---------------------------------------------------------------------------
# Atlantic newsletter subject keywords
# Emails matching these → "newsletter"; everything else → "longform"
# ---------------------------------------------------------------------------

ATLANTIC_NEWSLETTER_SUBJECTS = [
    "the atlantic daily",
    "notes from the editor",
    "one story to read today",
    "atlantic intelligence",
    "national security",
    "the unfinished revolution",
]

# ---------------------------------------------------------------------------
# Sender definitions
# All default to "newsletter" except breakingnews which is "breaking"
# Dynamic tier detection in _detect_tier() handles per-email overrides
# ---------------------------------------------------------------------------

PREMIUM_SENDERS = {
    "newsletters@technologyreview.com": {
        "name": "MIT Technology Review",
        "tier": "newsletter",
        "home_url": "https://www.technologyreview.com",
    },
    "nytdirect@nytimes.com": {
        "name": "New York Times",
        "tier": "newsletter",
        "home_url": "https://www.nytimes.com",
    },
    "breakingnews@nytimes.com": {
        "name": "New York Times",
        "tier": "breaking",
        "home_url": "https://www.nytimes.com",
    },
    "noreply@e.economist.com": {
        "name": "The Economist",
        "tier": "newsletter",
        "home_url": "https://www.economist.com",
    },
    "newsletters@e.economist.com": {
        "name": "The Economist",
        "tier": "newsletter",
        "home_url": "https://www.economist.com",
    },
    "email@theatlantic.com": {
        "name": "The Atlantic",
        "tier": "newsletter",   # overridden per-email by _detect_tier()
        "home_url": "https://www.theatlantic.com",
    },
    "news@foreignaffairs.com": {
        "name": "Foreign Affairs",
        "tier": "newsletter",
        "home_url": "https://www.foreignaffairs.com",
    },
    "@e1.theathletic.com": {
        "name": "The Athletic",
        "tier": "newsletter",
        "home_url": "https://theathletic.com",
    },
    # ── Add WSJ + FT here when re-subscribed ──
    # "newsletters@wsj.com": {
    #     "name": "Wall Street Journal",
    #     "tier": "newsletter",
    #     "home_url": "https://www.wsj.com",
    # },
    # "firstft@ft.com": {
    #     "name": "Financial Times",
    #     "tier": "newsletter",
    #     "home_url": "https://www.ft.com",
    # },
}

# ---------------------------------------------------------------------------
# Dynamic tier detection
# ---------------------------------------------------------------------------

def _detect_tier(source: dict, subject: str, from_header: str = "") -> str:
    """
    Determine the correct tier for an email based on source and subject.

    Priority order:
    1. Breaking news sender → always "breaking"
    2. NYT + "french" in subject → "longform" (David French column)
    3. Atlantic + known newsletter subject → "newsletter"
    4. Atlantic + unknown subject → "longform" (feature article)
    5. Everything else → "newsletter"
    """
    # Breaking always stays breaking
    if source.get("tier") == "breaking":
        return "breaking"

    subject_lower = subject.lower()

    # David French columns from NYT — detected by sender name in From header
    if source.get("name") == "New York Times" and "david french" in from_header.lower():
        return "longform"

    # Atlantic — known newsletters vs longform features
    if source.get("name") == "The Atlantic":
        if any(kw in subject_lower for kw in ATLANTIC_NEWSLETTER_SUBJECTS):
            return "newsletter"
        return "longform"

    # Default — everything else is a newsletter
    return "newsletter"

# ---------------------------------------------------------------------------
# Gmail auth
# ---------------------------------------------------------------------------

def _load_credentials(token_json_str: str) -> Credentials:
    info  = json.loads(token_json_str)
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def _get_services() -> list[tuple[object, str]]:
    services = []

    token1 = os.environ.get("GMAIL_TOKEN_JSON")
    if token1:
        try:
            creds = _load_credentials(token1)
            svc   = build("gmail", "v1", credentials=creds, cache_discovery=False)
            services.append((svc, "account-1"))
            print("[premium_gmail] Account 1 authenticated ✓")
        except Exception as e:
            print(f"[premium_gmail] Account 1 auth failed: {e}")

    token2 = os.environ.get("GMAIL_TOKEN_JSON_2")
    if token2:
        try:
            creds = _load_credentials(token2)
            svc   = build("gmail", "v1", credentials=creds, cache_discovery=False)
            services.append((svc, "account-2"))
            print("[premium_gmail] Account 2 authenticated ✓")
        except Exception as e:
            print(f"[premium_gmail] Account 2 auth failed: {e}")

    if not services:
        raise RuntimeError(
            "No Gmail tokens found. Set GMAIL_TOKEN_JSON and/or GMAIL_TOKEN_JSON_2."
        )

    return services

# ---------------------------------------------------------------------------
# Email parsing helpers
# ---------------------------------------------------------------------------

def _headers_dict(headers_list: list) -> dict:
    return {h["name"].lower(): h["value"] for h in headers_list}


def _decode_body(payload: dict) -> str:
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime_type == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    if mime_type == "text/html" and body_data:
        raw = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
        return _strip_html(raw)

    for part in payload.get("parts", []):
        result = _decode_body(part)
        if result:
            return result

    return ""


def _strip_html(html: str) -> str:
    html = re.sub(r"<(br|p|div|li|h[1-6])[^>]*>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", "", html)
    for ent, char in [("&amp;","&"),("&lt;","<"),("&gt;",">"),
                      ("&quot;",'"'),("&#39;","'"),("&nbsp;"," ")]:
        html = html.replace(ent, char)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def _parse_date(date_str: str) -> str:
    try:
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _extract_primary_url(body: str, home_url: str) -> str:
    match = re.search(r"https?://[^\s\"'<>]+", body)
    return match.group(0) if match else home_url


def _sender_address(from_header: str) -> str:
    m = re.search(r"<([^>]+)>", from_header)
    return m.group(1).lower() if m else from_header.lower().strip()


def _match_source(sender: str) -> tuple[str, dict] | tuple[None, None]:
    if sender in PREMIUM_SENDERS:
        return sender, PREMIUM_SENDERS[sender]
    for key, source in PREMIUM_SENDERS.items():
        if key.startswith("@") and sender.endswith(key):
            return key, source
    return None, None


def _is_promo(subject: str) -> bool:
    return any(kw in subject.lower() for kw in PROMO_SUBJECT_KEYWORDS)


def _is_within_tier_window(published_iso: str, tier: str) -> bool:
    try:
        published = datetime.fromisoformat(published_iso)
        cutoff    = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS_BY_TIER[tier])
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return published >= cutoff
    except Exception:
        return True


def _sender_query_terms() -> str:
    return " OR ".join(f"from:{key}" for key in PREMIUM_SENDERS)

# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------

def _fetch_from_service(service, account_label: str, pm_run: bool) -> list[dict]:
    max_hours = max(
        LOOKBACK_HOURS_BY_TIER["newsletter"],
        LOOKBACK_HOURS_BY_TIER["longform"],
        LOOKBACK_HOURS_BY_TIER["breaking"] if pm_run else 0,
    )

    cutoff   = datetime.now(timezone.utc) - timedelta(hours=max_hours)
    after_ts = int(cutoff.timestamp())

    sender_filter = _sender_query_terms()
    query = f"({sender_filter}) after:{after_ts} {PROMO_QUERY_EXCLUSIONS}"

    print(f"[premium_gmail] {account_label}: querying Gmail (max lookback: {max_hours}h)...")

    messages   = []
    page_token = None
    while True:
        kwargs = {"userId": "me", "q": query, "maxResults": 200}
        if page_token:
            kwargs["pageToken"] = page_token
        result     = service.users().messages().list(**kwargs).execute()
        messages  += result.get("messages", [])
        page_token  = result.get("nextPageToken")
        if not page_token:
            break

    print(f"[premium_gmail] {account_label}: {len(messages)} matching messages found")

    articles:      list[dict]     = []
    sender_counts: dict[str, int] = {}
    promo_skipped: int            = 0
    window_skipped: int           = 0
    breaking_skipped: int         = 0

    for msg_ref in messages:
        try:
            msg = service.users().messages().get(
                userId="me", id=msg_ref["id"], format="full"
            ).execute()
        except Exception as e:
            print(f"[premium_gmail]   Error fetching message {msg_ref['id']}: {e}")
            continue

        payload = msg.get("payload", {})
        headers = _headers_dict(payload.get("headers", []))
        sender  = _sender_address(headers.get("from", ""))

        matched_key, source = _match_source(sender)
        if not source:
            continue

        subject = headers.get("subject", "(no subject)")

        # Dynamic tier detection
        tier = _detect_tier(source, subject, headers.get("from", ""))

        # Skip breaking on AM run
        if tier == "breaking" and not pm_run:
            breaking_skipped += 1
            continue

        # Promo filter
        if _is_promo(subject):
            print(f"[premium_gmail]   [skipped-promo] {subject[:70]}")
            promo_skipped += 1
            continue

        published = _parse_date(headers.get("date", ""))

        # Tier-specific lookback window
        if not _is_within_tier_window(published, tier):
            window_skipped += 1
            continue

        # Tier-specific per-sender cap
        max_count = MAX_PER_SENDER_BY_TIER.get(tier, 5)
        count     = sender_counts.get(matched_key, 0)
        if count >= max_count:
            continue

        body = _decode_body(payload)
        if not body or len(body.strip()) < 80:
            continue

        primary_url = _extract_primary_url(body, source["home_url"])

        article = {
            "source":      source["name"],
            "title":       subject,
            "url":         primary_url,
            "published":   published,
            "content":     body[:8000],
            "description": body[:500],
            "tier":        tier,
            "sender":      sender,
        }

        articles.append(article)
        sender_counts[matched_key] = count + 1
        print(f"[premium_gmail]   [{tier}] {source['name']}: {subject[:70]}")

    if promo_skipped:
        print(f"[premium_gmail] {account_label}: {promo_skipped} promo email(s) skipped")
    if window_skipped:
        print(f"[premium_gmail] {account_label}: {window_skipped} email(s) outside tier window")
    if breaking_skipped:
        print(f"[premium_gmail] {account_label}: {breaking_skipped} breaking alert(s) skipped (AM run)")

    return articles

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_premium_gmail_articles() -> list[dict]:
    """
    Authenticate against all configured Gmail accounts and return
    all premium journalism articles tagged by tier.

    Breaking news only fetched on PM runs (UTC 22-23).
    Longform uses 72h lookback for weekly columns.
    """
    pm_run   = _is_pm_run()
    run_type = "PM" if pm_run else "AM"

    print(f"\n[premium_gmail] Starting {run_type} fetch...")
    print(f"  newsletter lookback : {LOOKBACK_HOURS_BY_TIER['newsletter']}h")
    print(f"  longform lookback   : {LOOKBACK_HOURS_BY_TIER['longform']}h")
    if pm_run:
        print(f"  breaking lookback   : {LOOKBACK_HOURS_BY_TIER['breaking']}h (PM run)")
    else:
        print(f"  breaking            : skipped (AM run)")

    try:
        services = _get_services()
    except RuntimeError as e:
        print(f"[premium_gmail] {e}")
        return []

    all_articles = []
    for service, label in services:
        articles = _fetch_from_service(service, label, pm_run)
        all_articles.extend(articles)

    tiers = {"newsletter": 0, "breaking": 0, "longform": 0}
    for a in all_articles:
        tiers[a.get("tier", "newsletter")] += 1

    print(f"\n[premium_gmail] Done. {len(all_articles)} total articles:")
    print(f"  newsletter : {tiers['newsletter']}")
    print(f"  breaking   : {tiers['breaking']}")
    print(f"  longform   : {tiers['longform']}")

    return all_articles