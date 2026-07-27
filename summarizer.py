"""
summarizer.py — OSINT summarization (Gemini, google-genai SDK)

Two-phase pipeline:

  Phase 1 — Per-article summary (parallel)
            → {source, title, url, published, summary} (2-3 sentences each)

  Phase 2 — Narrative synthesis tying all source summaries together (one call)
            → narrative_summary string
"""

import json
import os
import re
import concurrent.futures
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# Adjust if a newer Gemini model is available — check ai.google.dev for current names
MODEL = "gemini-2.0-flash"


def _clean_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw.strip())
    return raw


def _call(prompt: str, system: str) -> dict | None:
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
            ),
        )
        raw = _clean_json(response.text)
        return json.loads(raw)
    except Exception as e:
        print(f"  [summarizer] API call failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Phase 1: Per-article summary
# ---------------------------------------------------------------------------

SOURCE_SUMMARY_SYSTEM = """You are a precise news analyst. Summarize articles concisely.
Return ONLY valid JSON, no markdown, no preamble."""

SOURCE_SUMMARY_PROMPT = """Summarize this article in 2-3 sentences — direct, factual, no fluff,
no editorializing beyond what the source itself argues.

Return this JSON:
{{
  "summary": "2-3 sentence summary of the article's key point(s)"
}}

Source: {source}
Title: {title}
Published: {published}

Content:
{content}"""


def summarize_article(article: dict) -> dict | None:
    content = article.get("content", "") or article.get("description", "")
    if not content or len(content.strip()) < 100:
        return None

    prompt = SOURCE_SUMMARY_PROMPT.format(
        source=article.get("source", ""),
        title=article.get("title", ""),
        published=article.get("published", ""),
        content=content[:4000],
    )

    result = _call(prompt, SOURCE_SUMMARY_SYSTEM)
    if not result:
        return None

    return {
        "source":    article.get("source", "?"),
        "title":     article.get("title", ""),
        "url":       article.get("url", ""),
        "published": article.get("published", ""),
        "summary":   result.get("summary", ""),
    }


def run_summaries_parallel(articles: list[dict]) -> list[dict]:
    """Run per-article summarization in parallel, preserving article order where possible."""
    results = [None] * len(articles)

    def task(args):
        i, a = args
        return i, summarize_article(a)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(task, (i, a)): i for i, a in enumerate(articles)}
        for future in concurrent.futures.as_completed(futures):
            try:
                i, result = future.result()
                results[i] = result
            except Exception as e:
                print(f"  [summarize] Thread error: {e}")

    return [r for r in results if r is not None]


# ---------------------------------------------------------------------------
# Phase 2: Narrative synthesis
# ---------------------------------------------------------------------------

NARRATIVE_SYSTEM = """You are a senior intelligence analyst writing a concise narrative synthesis.
Write in direct, analytical prose. Name the throughline — don't just list stories.
Return ONLY valid JSON, no markdown, no preamble."""

NARRATIVE_PROMPT = """Below are today's per-source article summaries. Write a single narrative
paragraph (4-6 sentences) that connects the major threads across these stories.

Return this JSON:
{{
  "narrative_summary": "4-6 sentence narrative connecting today's stories..."
}}

Source summaries:
{summaries}"""


def synthesize_narrative(source_summaries: list[dict]) -> str:
    summaries_text = "\n".join(
        f"- {s['source']}: {s['summary']}" for s in source_summaries
    )
    prompt = NARRATIVE_PROMPT.format(summaries=summaries_text)
    result = _call(prompt, NARRATIVE_SYSTEM)
    return result.get("narrative_summary", "") if result else ""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_briefing(articles: list[dict], date: str) -> dict:
    """
    Simplified pipeline:
      Phase 1 — per-article 2-3 sentence summaries (parallel)
      Phase 2 — narrative paragraph tying them together
    """
    print(f"\n[summarizer] Summarizing {len(articles)} articles (parallel)...")
    source_summaries = run_summaries_parallel(articles)
    print(f"[summarizer] {len(source_summaries)}/{len(articles)} summarized")

    if not source_summaries:
        return {
            "date": date,
            "error": "No articles could be summarized",
            "narrative_summary": "",
            "source_summaries": [],
            "articles_processed": 0,
        }

    print(f"\n[summarizer] Writing narrative summary...")
    narrative_summary = synthesize_narrative(source_summaries)
    print(f"[summarizer] Done. {len(source_summaries)} source summaries generated.")

    return {
        "date":               date,
        "narrative_summary":  narrative_summary,
        "source_summaries":   source_summaries,
        "articles_processed": len(source_summaries),
        "articles_attempted": len(articles),
        "publications":       list(set(s["source"] for s in source_summaries)),
    }