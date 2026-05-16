"""
summarizer.py

Two-phase synthesis pipeline:
  Phase 1 - Lightweight per-article extraction (title, url, source, key claims)
  Phase 2 - One synthesis call: group into themes, write executive briefing with inline citations
"""

import json
import os
import anthropic

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Phase 1: Extract key claims from a single article
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM = """You are a precise news analyst. Given an article, extract structured metadata.
Return ONLY valid JSON, no markdown, no preamble."""

EXTRACTION_PROMPT = """Extract the following from this article and return as JSON:
{{
  "title": "article title",
  "url": "article url",
  "publication": "publication name",
  "date": "publication date if available, else null",
  "key_claims": ["3 specific factual claims or arguments made in the article"],
  "topics": ["2-3 topic tags, e.g. 'Iran War', 'Trump approval', 'redistricting', 'economy'"]
}}

Article metadata:
Title: {title}
URL: {url}
Publication: {source}
Date: {date}

Article content:
{content}"""


def extract_article(article: dict) -> dict | None:
    """Phase 1: Extract key claims from one article. Returns structured dict or None on failure."""
    content = article.get("content", "") or article.get("description", "")
    if not content or len(content.strip()) < 100:
        return None

    content_truncated = content[:4000]

    prompt = EXTRACTION_PROMPT.format(
        title=article.get("title", ""),
        url=article.get("url", ""),
        source=article.get("source", ""),
        date=article.get("published", ""),
        content=content_truncated,
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        print(f"  [extract] Failed for '{article.get('title', 'unknown')}': {e}")
        return None


# ---------------------------------------------------------------------------
# Phase 2: Synthesize all extractions into a themed executive briefing
# ---------------------------------------------------------------------------

SYNTHESIS_SYSTEM = """You are a senior intelligence analyst producing a daily executive briefing.
You write in an analytical, direct style — not journalistic fluff, not bullet lists.
Return ONLY valid JSON, no markdown, no preamble."""

SYNTHESIS_PROMPT = """Below is today's extracted news intelligence from multiple sources.

Your task:
1. Identify 4-6 major themes that cut across these sources (e.g. "Iran War & U.S. Foreign Policy", "Trump Domestic Corruption", "2026 Midterms & Redistricting", "Economy & Markets", "Democracy & Rule of Law", "Tech & AI", "World Affairs")
2. For each theme, write a 2-3 paragraph synthesized executive briefing in analytical prose
3. Cite sources inline using this exact format: [Publication: Title](url)
4. Each theme should synthesize across multiple sources where possible
5. Be specific — use names, numbers, claims from the source material
6. End with a "Big Picture" section connecting the day's major threads

Return this JSON structure:
{{
  "date": "{date}",
  "themes": [
    {{
      "theme": "Theme Name",
      "briefing": "2-3 paragraphs of analytical prose with [inline citations](url)...",
      "source_count": 3,
      "publications": ["Pub1", "Pub2"]
    }}
  ],
  "big_picture": "1-2 paragraph synthesis of the day's overarching narrative with citations"
}}

Today's extracted intelligence ({article_count} articles from {source_count} publications):

{extractions_json}"""


def _trim_extractions(extractions: list[dict]) -> list[dict]:
    """Trim extractions to reduce synthesis prompt size — 3 claims max, shorter topics."""
    trimmed = []
    for e in extractions:
        trimmed.append({
            "title": e.get("title", ""),
            "url": e.get("url", ""),
            "publication": e.get("publication", ""),
            "key_claims": e.get("key_claims", [])[:3],
            "topics": e.get("topics", [])[:2],
        })
    return trimmed


def synthesize_briefing(extractions: list[dict], date: str) -> dict | None:
    """Phase 2: Synthesize all article extractions into a themed executive briefing."""
    if not extractions:
        return None

    publications = list(set(e.get("publication", "Unknown") for e in extractions))
    trimmed = _trim_extractions(extractions)

    prompt = SYNTHESIS_PROMPT.format(
        date=date,
        article_count=len(trimmed),
        source_count=len(publications),
        extractions_json=json.dumps(trimmed, indent=2),
    )

    print(f"  [synthesize] Prompt size: ~{len(prompt)//4} tokens estimated")

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,  # bumped from 4000 — themed briefings need room
            system=SYNTHESIS_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        print(f"  [synthesize] Response size: ~{len(raw)//4} tokens estimated, stop_reason={response.stop_reason}")

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except json.JSONDecodeError as e:
        print(f"  [synthesize] JSON parse error: {e}")
        print(f"  [synthesize] Raw response (first 500 chars): {raw[:500]}")
        return None
    except Exception as e:
        print(f"  [synthesize] API error: {type(e).__name__}: {e}")
        return None


# ---------------------------------------------------------------------------
# Main entry point called from main.py
# ---------------------------------------------------------------------------

def generate_briefing(articles: list[dict], date: str) -> dict:
    """
    Full pipeline:
      1. Extract key claims from each article (Phase 1)
      2. Synthesize into themed briefing (Phase 2)
    """
    print(f"\n[summarizer] Phase 1: Extracting from {len(articles)} articles...")
    extractions = []
    for i, article in enumerate(articles):
        print(f"  [{i+1}/{len(articles)}] {article.get('source', '?')} — {article.get('title', '')[:60]}")
        result = extract_article(article)
        if result:
            extractions.append(result)

    print(f"\n[summarizer] Phase 1 complete: {len(extractions)}/{len(articles)} articles extracted")

    if not extractions:
        return {
            "date": date,
            "error": "No articles could be extracted",
            "themes": [],
            "big_picture": "",
            "articles_processed": 0,
        }

    print(f"\n[summarizer] Phase 2: Synthesizing {len(extractions)} extractions into themed briefing...")
    briefing = synthesize_briefing(extractions, date)

    if not briefing:
        return {
            "date": date,
            "error": "Synthesis failed",
            "themes": [],
            "big_picture": "",
            "extractions": extractions,
            "articles_processed": len(extractions),
        }

    briefing["articles_processed"] = len(extractions)
    briefing["articles_attempted"] = len(articles)
    briefing["publications"] = list(set(e.get("publication", "?") for e in extractions))

    print(f"[summarizer] Done. {len(briefing.get('themes', []))} themes generated.")
    return briefing