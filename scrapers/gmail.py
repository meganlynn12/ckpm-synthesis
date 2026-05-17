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

LOOKBACK_HOURS = 24
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_credentials() -> Credentials:
    """
    Build Gmail credentials from GitHub Secrets injected as env vars.
    GMAIL_TOKEN and GMAIL_CREDENTIALS must be set in the environment.
    """
    token_data = json.loads(os.environ["GMAIL_TOKEN"])

    creds = Credentials(
        token=token_data["token"],
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data["scopes"],
    )

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return creds


def strip_html(html: str) -> str:
    text = BeautifulSoup(html, "lxml").get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def decode_part(part: dict) -> str:
    """Decode a base64url-encoded email body part."""
    data = part.get("body", {}).get("data", "")
    if not data:
        return ""
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")


def extract_body(payload: dict) -> str:
    """
    Recursively extract the best text content from an email payload.
    Prefers text/html over text/plain for richer content.
    """
    mime = payload.get("mimeType", "")

    if mime == "text/html":
        return decode_part(payload)

    if mime == "text/plain":
        return decode_part(payload)

    if "parts" in payload:
        # Prefer html part
        html_content = ""
        plain_content = ""
        for part in payload["parts"]:
            result = extract_body(part)
            if part.get("mimeType") == "text/html" or "html" in part.get("mimeType", ""):
                html_content = result
            elif part.get("mimeType") == "text/plain":
                plain_content = result
            elif result:
                html_content = html_content or result
        return html_content or plain_content

    return ""


def parse_gmail_date(date_str: str) -> datetime | None:
    """Parse Gmail's internalDate (milliseconds since epoch)."""
    try:
        return datetime.fromtimestamp(int(date_str) / 1000, tz=timezone.utc)
    except Exception:
        return None


def get_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def fetch_gmail_articles() -> list[dict]:
    """
    Fetch Substack newsletter emails from Gmail from the last LOOKBACK_HOURS.
    Returns a flat list of article dicts matching the rss.py format.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    cutoff_epoch_ms = int(cutoff.timestamp())

    print(f"[gmail] Fetching Substack emails after {cutoff.strftime('%Y-%m-%d %H:%M UTC')}")

    try:
        creds = get_credentials()
        service = build("gmail", "v1", credentials=creds)
    except Exception as e:
        print(f"[gmail] ✗ Auth failed: {e}")
        return []

    # Search for emails from any @substack.com sender in the time window
    query = f"from:@substack.com after:{cutoff_epoch_ms // 1000}"

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

    print(f"[gmail] Found {len(messages)} Substack emails")

    articles = []
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

            # Extract newsletter name from sender
            # e.g. "Heather Cox Richardson <heathercoxrichardson@substack.com>"
            name_match = re.match(r"^(.+?)\s*<", sender)
            source_name = name_match.group(1).strip() if name_match else sender

            body_html = extract_body(msg["payload"])
            content_text = strip_html(body_html)[:MAX_CONTENT_CHARS]

            if not content_text:
                continue

            # Best-effort: extract the canonical URL from the email
            url_match = re.search(r"https://[a-z0-9\-]+\.substack\.com/p/[^\s\"'>]+", body_html)
            url = url_match.group(0).split("?")[0] if url_match else ""

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

    print(f"[gmail] ✓ {len(articles)} articles extracted")
    return articles
