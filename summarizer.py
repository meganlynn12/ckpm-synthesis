"""
summarizer.py

Two-phase synthesis pipeline:
  Phase 1 - Lightweight per-article extraction (title, url, source, key claims)
  Phase 2 - One synthesis call: group into themes, write executive briefing
             with numbered inline superscript citations [1] and bibliography
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
  "key_claims": ["3-5 specific factual claims or arguments made in the article"],
  "topics": ["2-4 topic tags, e.g. 'Iran War', 'Trump approval', 'redistricting', 'economy'"]
}}

Article metadata:
Title: {title}
URL: {url}
Publication: {source}
Date: {date}

Article content:
{content}"""


def extract_article(article: dict) -> dict | None:
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

Each source has been assigned a reference number based on its position in the list.
Use these numbers as inline superscript citations in your briefing text, like this: [1] or [2,3].

Your task:
1. Identify 4-6 major themes that cut across these sources
2. For each theme, write a 2-4 paragraph synthesized executive briefing in analytical prose
3. Cite sources inline using superscript numbers like [1] or [2,3] — NOT markdown links
4. At the end of each theme's briefing, include a "references" list: an array of the source
   numbers actually cited in that theme's briefing, in order of appearance
5. Be specific — use names, numbers, claims from the source material
6. End with a "Big Picture" section connecting the day's major threads, also with inline citations

Return this exact JSON structure:
{{
  "date": "{date}",
  "themes": [
    {{
      "theme": "Theme Name",
      "briefing": "Analytical prose with inline citations like [1] or [2,3]...",
      "references": [
        {{"num": 1, "publication": "Publication Name", "title": "Article Title", "url": "https://..."}},
        {{"num": 3, "publication": "Publication Name", "title": "Article Title", "url": "https://..."}}
      ],
      "publications": ["Pub1", "Pub2"]
    }}
  ],
  "big_picture": "1-2 paragraph synthesis with inline citations like [1]"
}}

Today's sources (use these numbers for citations):
{numbered_sources}

Full extracted intelligence ({article_count} articles):
{extractions_json}"""


def synthesize_briefing(extractions: list[dict], date: str) -> dict | None:
    if not extractions:
        return None

    # Build numbered source list for the prompt
    numbered_sources = "\n".join(
        f"[{i+1}] {e.get('publication', 'Unknown')} — \"{e.get('title', '')}\" {e.get('url', '')}"
        for i, e in enumerate(extractions)
    )

    publications = list(set(e.get("publication", "Unknown") for e in extractions))

    prompt = SYNTHESIS_PROMPT.format(
        date=date,
        article_count=len(extractions),
        numbered_sources=numbered_sources,
        extractions_json=json.dumps(extractions, indent=2),
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            system=SYNTHESIS_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        print(f"  [synthesize] Response size: ~{len(raw)} chars, stop_reason={response.stop_reason}")
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        cleaned = raw.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as je:
            print(f"  [synthesize] JSON parse error at position {je.pos}: {je.msg}")
            print(f"  [synthesize] Near: {cleaned[max(0,je.pos-50):je.pos+50]}")
            return None
    except Exception as e:
        print(f"  [synthesize] Synthesis failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_briefing(articles: list[dict], date: str) -> dict:
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
    # Cap to avoid token limits in synthesis prompt
    if len(extractions) > 20:
        print(f"[summarizer] Capping extractions to 20 for synthesis")
        extractions = extractions[:20]
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