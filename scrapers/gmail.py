# scrapers/gmail.py
# Fetches Substack newsletter emails from Gmail.
# Looks for any email from @substack.com in the last 24 hours.

import os
import json
import base64
import re
from datetime import datetime, timezone, timedelta

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from bs4 import BeautifulSoup

from config import MAX_CONTENT_CHARS

LOOKBACK_HOURS = 13
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Minimum content length to be considered a real article
MIN_CONTENT_CHARS = 500

# Subject patterns to skip — transactional/system emails
SKIP_SUBJECT_PATTERNS = [
    r"verification code",
    r"confirm email",
    r"confirm your email",
    r"you're on the list",
    r"youre on the list",
    r"welcome to",
    r"verify your",
    r"live video",
    r"is now live",
    r"caption contest",
    r"^\d{6} is your",       # OTP codes like "140918 is your..."
    r"^re:",
    r"^fwd:",
]

SKIP_SUBJECT_RE = re.compile(
    "|".join(SKIP_SUBJECT_PATTERNS), re.IGNORECASE
)


def get_credentials() -> Credentials:
    token_data = json.loads(os.environ["GMAIL_TOKEN"])
    creds = Credentials(
        token=token_data["token"],
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data["scopes"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def strip_html(html: str) -> str:
    text = BeautifulSoup(html, "lxml").get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def decode_part(part: dict) -> str:
    data = part.get("body", {}).get("data", "")
    if not data:
        return ""
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")


def extract_body(payload: dict) -> str:
    mime = payload.get("mimeType", "")
    if mime == "text/html":
        return decode_part(payload)
    if mime == "text/plain":
        return decode_part(payload)
    if "parts" in payload:
        html_content = ""
        plain_content = ""
        for part in payload["parts"]:
            result = extract_body(part)
            part_mime = part.get("mimeType", "")
            if "html" in part_mime:
                html_content = html_content or result
            elif "plain" in part_mime:
                plain_content = plain_content or result
            elif result:
                html_content = html_content or result
        return html_content or plain_content
    return ""


def parse_gmail_date(date_str: str) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(date_str) / 1000, tz=timezone.utc)
    except Exception:
        return None


def get_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def clean_sender_name(sender: str) -> str:
    """Extract clean publication name from Gmail sender field."""
    # "Heather Cox Richardson <heathercoxrichardson@substack.com>"
    name_match = re.match(r"^(.+?)\s*<", sender)
    if name_match:
        name = name_match.group(1).strip().strip('"')
        # Remove common suffixes
        name = re.sub(r"\s*(newsletter|substack|via substack)$", "", name, flags=re.IGNORECASE)
        return name.strip()
    # Just an email address
    email_match = re.match(r"([^@]+)@", sender)
    return email_match.group(1) if email_match else sender


def fetch_gmail_articles() -> list[dict]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    cutoff_epoch_sec = int(cutoff.timestamp())

    print(f"[gmail] Fetching Substack emails after {cutoff.strftime('%Y-%m-%d %H:%M UTC')}")

    try:
        creds = get_credentials()
        service = build("gmail", "v1", credentials=creds)
    except Exception as e:
        print(f"[gmail] ✗ Auth failed: {e}")
        return []

    # query = f"from:@substack.com after:{cutoff_epoch_sec}"
    query = f"(from:@substack.com OR from:goodpolitics@virginia.edu) after:{cutoff_epoch_sec}"

    try:
        result = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=50,
        ).execute()
    except Exception as e:
        print(f"[gmail] ✗ Search failed: {e}")
        return []

    messages = result.get("messages", [])
    if not messages:
        print(f"[gmail] ✓ No Substack emails in last {LOOKBACK_HOURS}h")
        return []

    print(f"[gmail] Found {len(messages)} Substack emails, filtering...")

    articles = []
    skipped = 0

    for msg_ref in messages:
        try:
            msg = service.users().messages().get(
                userId="me",
                id=msg_ref["id"],
                format="full",
            ).execute()

            headers = msg["payload"].get("headers", [])
            subject = get_header(headers, "subject") or "Untitled"
            sender = get_header(headers, "from")
            date_ms = msg.get("internalDate", "0")
            pub = parse_gmail_date(date_ms)

            # Skip transactional/system emails
            if SKIP_SUBJECT_RE.search(subject):
                skipped += 1
                continue

            source_name = clean_sender_name(sender)

            body_html = extract_body(msg["payload"])
            content_text = strip_html(body_html)[:MAX_CONTENT_CHARS]

            # Skip if content is too short to be a real article
            if len(content_text) < MIN_CONTENT_CHARS:
                skipped += 1
                continue

            # Extract canonical URL
            url_match = re.search(
                r"https://[a-z0-9\-]+\.substack\.com/p/[^\s\"'>?]+",
                body_html
            )
            url = url_match.group(0) if url_match else ""

            articles.append({
                "source": source_name,
                "title": subject,
                "url": url,
                "published": pub.isoformat() if pub else "",
                "content": content_text,
                "summarized": False,
                "bullets": [],
                "themes": [],
            })

            print(f"    ✓ {source_name} — {subject[:60]}")

        except Exception as e:
            print(f"    ✗ Error processing message {msg_ref['id']}: {e}")

    print(f"[gmail] ✓ {len(articles)} articles extracted, {skipped} skipped")
    return articles