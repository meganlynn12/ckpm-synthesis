"""
summarizer_premium.py

Three-tier synthesis pipeline for premium journalism content.

Tier 1 — parse_newsletter(article)
    Extracts structured headline items from a newsletter email body.
    No summarization — structure extraction only.
    Output: list of {headline, blurb, url}

Tier 2 — synthesize_breaking(articles)
    Collapses multiple intraday breaking news alerts into a coherent
    end-of-day narrative with inline citations.
    Output: {narrative, references}

Tier 3 — synthesize_longform(article)
    Deep per-article analytical synthesis.
    Output: {thesis, context, arguments, significance, questions_raised}

Top level — synthesize_executive_summary(newsletters, breaking, longform)
    One-paragraph cross-cutting thread connecting all three sections.
    Output: string
"""

import json
import os
import concurrent.futures

import anthropic

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL  = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _call(system: str, prompt: str, max_tokens: int = 1000) -> dict | str | None:
    """Make a Claude API call and return parsed JSON or raw text."""
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return raw.strip()
    except Exception as e:
        print(f"  [summarizer_premium] API call failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Tier 1: Newsletter structure extraction
# ---------------------------------------------------------------------------

_NEWSLETTER_SYSTEM = """You are a precise content extractor.
Extract structured items from a newsletter email body.
Return ONLY valid JSON, no markdown, no preamble."""

_NEWSLETTER_PROMPT = """Extract the individual story items from this newsletter email.
Each item should have a headline, a brief description (the blurb as written — do not paraphrase),
and the article URL if one is present in the text near that item.

Return this JSON:
{{
  "items": [
    {{
      "headline": "Story headline as written",
      "blurb": "Brief description as written in the newsletter",
      "url": "https://... or null if not found"
    }}
  ]
}}

Include all substantive story items. Skip navigation links, subscription footers,
and promotional content.

Newsletter source: {source}
Newsletter subject: {title}

Email body:
{content}"""


def parse_newsletter(article: dict) -> dict:
    """
    Tier 1: Extract structured items from a newsletter email.
    Returns the article dict augmented with an 'items' list.
    No summarization — structure extraction only.
    """
    prompt = _NEWSLETTER_PROMPT.format(
        source=article.get("source", ""),
        title=article.get("title", ""),
        content=article.get("content", "")[:6000],
    )

    result = _call(_NEWSLETTER_SYSTEM, prompt, max_tokens=1500)

    if isinstance(result, dict) and "items" in result:
        items = result["items"]
    else:
        items = [{"headline": article.get("title", ""), "blurb": "", "url": article.get("url")}]

    return {
        "source":    article["source"],
        "title":     article["title"],
        "published": article.get("published", ""),
        "url":       article.get("url", ""),
        "items":     items,
        "tier":      "newsletter",
    }


def parse_newsletters_parallel(articles: list[dict]) -> list[dict]:
    """Run Tier 1 parsing in parallel across all newsletter articles."""
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(parse_newsletter, a): a for a in articles}
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
                print(f"  ✓ Newsletter parsed: {futures[future].get('source')} — {futures[future].get('title', '')[:50]}")
            except Exception as e:
                print(f"  [newsletter] Thread error: {e}")
    return results


# ---------------------------------------------------------------------------
# Tier 2: Breaking news end-of-day digest
# ---------------------------------------------------------------------------

_BREAKING_SYSTEM = """You are a senior news editor writing an end-of-day briefing.
Write in direct, factual prose. No speculation. Use inline citations like [1] or [2,3].
Return ONLY valid JSON, no markdown, no preamble."""

_BREAKING_PROMPT = """You have received {count} breaking news alerts throughout the day.
Write a concise end-of-day digest that:
- Groups related alerts into coherent story threads
- Explains what happened, in sequence where relevant
- Uses inline citations like [1] or [2,3] to reference specific alerts
- Is 2-3 paragraphs maximum

Return this JSON:
{{
  "narrative": "2-3 paragraph digest with inline citations...",
  "references": [
    {{
      "num": 1,
      "title": "Alert headline",
      "url": "https://...",
      "source": "New York Times",
      "published": "ISO date string"
    }}
  ]
}}

Only include in references the alerts you actually cite.

Breaking news alerts (numbered for citation):
{numbered_alerts}"""


def synthesize_breaking(articles: list[dict]) -> dict | None:
    if not articles:
        return None

    numbered_alerts = "\n".join(
        f"[{i+1}] {a.get('source','?')} — {a.get('title','')} ({a.get('published','')})\n"
        f"     URL: {a.get('url','')}"
        for i, a in enumerate(articles)
    )

    prompt = _BREAKING_PROMPT.format(
        count=len(articles),
        numbered_alerts=numbered_alerts,
    )

    result = _call(_BREAKING_SYSTEM, prompt, max_tokens=1200)

    if not isinstance(result, dict):
        return None

    result["tier"]        = "breaking"
    result["alert_count"] = len(articles)
    return result


# ---------------------------------------------------------------------------
# Tier 3: Longform deep synthesis
# ---------------------------------------------------------------------------

_LONGFORM_SYSTEM = """You are a senior intelligence analyst synthesizing long-form journalism.
Write analytically and precisely. Avoid hedging language and filler phrases.
Return ONLY valid JSON, no markdown, no preamble."""

_LONGFORM_PROMPT = """Synthesize this long-form article into a structured analytical brief.

Return this JSON:
{{
  "thesis": "The article's core argument in one precise sentence.",
  "context": "What prompted this piece — the event, debate, or moment it responds to (1-2 sentences).",
  "arguments": [
    "Key argument or finding #1, with the evidence or logic the author uses",
    "Key argument or finding #2",
    "Key argument or finding #3 (add more if genuinely distinct)"
  ],
  "significance": "Why this piece matters now — what it illuminates, challenges, or predicts (2-3 sentences).",
  "questions_raised": [
    "An unresolved tension or question the piece leaves open",
    "A second one if present"
  ]
}}

Be specific. Avoid vague summaries. Quote the author's actual framing where it sharpens the synthesis.

Article metadata:
  Source:    {source}
  Title:     {title}
  URL:       {url}
  Published: {published}

Article content:
{content}"""


def synthesize_longform_article(article: dict) -> dict | None:
    prompt = _LONGFORM_PROMPT.format(
        source=article.get("source", ""),
        title=article.get("title", ""),
        url=article.get("url", ""),
        published=article.get("published", ""),
        content=article.get("content", "")[:7000],
    )

    result = _call(_LONGFORM_SYSTEM, prompt, max_tokens=1500)

    if not isinstance(result, dict):
        return None

    return {
        "source":    article["source"],
        "title":     article["title"],
        "url":       article.get("url", ""),
        "published": article.get("published", ""),
        "tier":      "longform",
        **result,
    }


def synthesize_longform_parallel(articles: list[dict]) -> list[dict]:
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(synthesize_longform_article, a): a for a in articles}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if result:
                    results.append(result)
                    print(f"  ✓ Longform synthesized: {futures[future].get('source')} — {futures[future].get('title','')[:50]}")
            except Exception as e:
                print(f"  [longform] Thread error: {e}")
    return results


# ---------------------------------------------------------------------------
# Top level: Executive summary
# ---------------------------------------------------------------------------

_EXEC_SYSTEM = """You are a senior analyst writing a one-paragraph executive summary.
Write in direct, confident prose. Identify the single most important connecting thread
across today's content. No bullet points. No hedging.
Return ONLY valid JSON, no markdown, no preamble."""

_EXEC_PROMPT = """Based on today's three content sections — newsletters, breaking news,
and long-form analysis — write a single paragraph (4-6 sentences) that identifies
the most important connecting thread or story of the day.

Be specific. Name the thread. Explain why it matters. Connect at least two of the
three sections if possible.

Today's content summary:

NEWSLETTERS ({newsletter_count} editions from: {newsletter_sources}):
{newsletter_headlines}

BREAKING NEWS ({breaking_count} alerts):
{breaking_summary}

LONGFORM ARTICLES ({longform_count} pieces from: {longform_sources}):
{longform_theses}

Return this JSON:
{{
  "executive_summary": "One paragraph connecting today's most important thread..."
}}"""


def synthesize_executive_summary(
    newsletters: list[dict],
    breaking:    dict | None,
    longform:    list[dict],
) -> str:
    newsletter_headlines = "\n".join(
        f"- {n['source']}: {n['title']}"
        for n in newsletters
    ) or "None today."

    breaking_summary = (
        breaking.get("narrative", "")[:400] + "..."
        if breaking and breaking.get("narrative")
        else "No breaking news alerts today."
    )

    longform_theses = "\n".join(
        f"- {a['source']}: {a.get('thesis', a.get('title',''))}"
        for a in longform
    ) or "None today."

    prompt = _EXEC_PROMPT.format(
        newsletter_count=len(newsletters),
        newsletter_sources=", ".join(set(n["source"] for n in newsletters)) or "none",
        newsletter_headlines=newsletter_headlines,
        breaking_count=breaking.get("alert_count", 0) if breaking else 0,
        breaking_summary=breaking_summary,
        longform_count=len(longform),
        longform_sources=", ".join(set(a["source"] for a in longform)) or "none",
        longform_theses=longform_theses,
    )

    result = _call(_EXEC_SYSTEM, prompt, max_tokens=400)

    if isinstance(result, dict):
        return result.get("executive_summary", "")
    return result or ""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_premium_briefing(articles: list[dict], date: str) -> dict:
    newsletter_articles = [a for a in articles if a.get("tier") == "newsletter"]
    breaking_articles   = [a for a in articles if a.get("tier") == "breaking"]
    longform_articles   = [a for a in articles if a.get("tier") == "longform"]

    print(f"\n[summarizer_premium] Routing: "
          f"{len(newsletter_articles)} newsletter, "
          f"{len(breaking_articles)} breaking, "
          f"{len(longform_articles)} longform")

    newsletters = []
    if newsletter_articles:
        print(f"\n[summarizer_premium] Tier 1: parsing {len(newsletter_articles)} newsletter(s)...")
        newsletters = parse_newsletters_parallel(newsletter_articles)

    breaking_digest = None
    if breaking_articles:
        print(f"\n[summarizer_premium] Tier 2: synthesizing {len(breaking_articles)} breaking alert(s)...")
        breaking_digest = synthesize_breaking(breaking_articles)
        if breaking_digest:
            print(f"  ✓ Breaking news digest complete")

    longform = []
    if longform_articles:
        print(f"\n[summarizer_premium] Tier 3: synthesizing {len(longform_articles)} longform article(s)...")
        longform = synthesize_longform_parallel(longform_articles)

    executive_summary = ""
    if newsletters or breaking_digest or longform:
        print(f"\n[summarizer_premium] Writing executive summary...")
        executive_summary = synthesize_executive_summary(newsletters, breaking_digest, longform)
        print(f"  ✓ Executive summary complete")

    print(f"\n[summarizer_premium] Done.")

    return {
        "date":              date,
        "pipeline":          "premium",
        "executive_summary": executive_summary,
        "newsletters":       newsletters,
        "breaking_digest":   breaking_digest,
        "longform":          longform,
        "counts": {
            "newsletter": len(newsletters),
            "breaking":   len(breaking_articles),
            "longform":   len(longform),
        },
    }