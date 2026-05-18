"""
summarizer.py

Hierarchical three-phase synthesis pipeline:

  Phase 1 - Lightweight per-article extraction (parallel)
            → {title, url, publication, key_claims, topics}

  Phase 2a - Cluster extractions into themes (one cheap call)
             → {theme_name: [article_indices]}

  Phase 2b - Synthesize each theme independently (one call per theme, parallel)
             → {theme, briefing, references, publications}

  Phase 3  - Write Big Picture from theme summaries only (one call)
             → big_picture string
"""

import json
import os
import concurrent.futures
import anthropic

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Phase 1: Extract key claims from a single article
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM = """You are a precise news analyst. Extract structured metadata from articles.
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

    prompt = EXTRACTION_PROMPT.format(
        title=article.get("title", ""),
        url=article.get("url", ""),
        source=article.get("source", ""),
        date=article.get("published", ""),
        content=content[:4000],
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


def run_phase1_parallel(articles: list[dict]) -> list[dict]:
    """Run Phase 1 extractions in parallel using a thread pool."""
    results = [None] * len(articles)

    def extract_with_index(args):
        i, article = args
        return i, extract_article(article)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(extract_with_index, (i, a)): i for i, a in enumerate(articles)}
        for future in concurrent.futures.as_completed(futures):
            try:
                i, result = future.result()
                results[i] = result
            except Exception as e:
                print(f"  [extract] Thread error: {e}")

    return [r for r in results if r is not None]


# ---------------------------------------------------------------------------
# Phase 2a: Cluster extractions into themes
# ---------------------------------------------------------------------------

CLUSTER_SYSTEM = """You are a senior news editor grouping articles into coherent themes.
Return ONLY valid JSON, no markdown, no preamble."""

CLUSTER_PROMPT = """Below are {count} news article extractions. Group them into 4-6 meaningful themes.

Each article is identified by its index number (0-based).
Assign every article to exactly one theme. No article should be left out.

Return this JSON structure:
{{
  "themes": [
    {{
      "theme": "Theme Name",
      "article_indices": [0, 3, 7]
    }}
  ]
}}

Good theme names are specific and analytical, e.g.:
- "Trump's Political Standing & 2026 Midterms"
- "Iran War: Military Escalation and Diplomacy"
- "Institutional Erosion: DOJ, FBI & Rule of Law"
- "Economy, Markets & Federal Reserve"

Articles:
{article_list}"""


def cluster_extractions(extractions: list[dict]) -> list[dict]:
    """
    Phase 2a: Group extractions into themes.
    Returns list of {theme, article_indices}.
    """
    article_list = "\n".join(
        f"[{i}] {e.get('publication', '?')} — \"{e.get('title', '')}\" | Topics: {', '.join(e.get('topics', []))}"
        for i, e in enumerate(extractions)
    )

    prompt = CLUSTER_PROMPT.format(
        count=len(extractions),
        article_list=article_list,
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=CLUSTER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        themes = result.get("themes", [])
        print(f"[summarizer] Phase 2a: {len(themes)} themes identified")
        for t in themes:
            print(f"  → {t['theme']} ({len(t['article_indices'])} articles)")
        return themes
    except Exception as e:
        print(f"[summarizer] Phase 2a clustering failed: {e}")
        # Fallback: put everything in one theme
        return [{"theme": "Today's Briefing", "article_indices": list(range(len(extractions)))}]


# ---------------------------------------------------------------------------
# Phase 2b: Synthesize a single theme
# ---------------------------------------------------------------------------

THEME_SYSTEM = """You are a senior intelligence analyst writing one section of a daily executive briefing.
Write in analytical, direct prose — not journalistic fluff, not bullet lists.
Return ONLY valid JSON, no markdown, no preamble."""

THEME_PROMPT = """Write an executive briefing for the theme "{theme}" using only the sources below.

Each source has a reference number. Use inline superscript citations like [1] or [2,3] in your prose.

Return this JSON:
{{
  "theme": "{theme}",
  "briefing": "2-4 paragraphs of analytical prose with inline citations like [1] or [2,3]...",
  "references": [
    {{"num": 1, "publication": "Publication Name", "title": "Article Title", "url": "https://..."}}
  ],
  "publications": ["Pub1", "Pub2"]
}}

Only include in "references" the sources you actually cite.

Sources for this theme:
{numbered_sources}

Full article details:
{extractions_json}"""


def synthesize_theme(theme_name: str, theme_extractions: list[dict], ref_offset: int) -> dict | None:
    """
    Phase 2b: Synthesize one theme.
    ref_offset ensures reference numbers are globally unique across themes.
    """
    numbered_sources = "\n".join(
        f"[{i + ref_offset + 1}] {e.get('publication', '?')} — \"{e.get('title', '')}\" {e.get('url', '')}"
        for i, e in enumerate(theme_extractions)
    )

    # Add ref numbers to extractions for the prompt
    extractions_with_refs = []
    for i, e in enumerate(theme_extractions):
        e_copy = dict(e)
        e_copy["ref_num"] = i + ref_offset + 1
        extractions_with_refs.append(e_copy)

    prompt = THEME_PROMPT.format(
        theme=theme_name,
        numbered_sources=numbered_sources,
        extractions_json=json.dumps(extractions_with_refs, indent=2),
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=THEME_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        return result
    except Exception as e:
        print(f"  [theme] Failed for '{theme_name}': {e}")
        return None


def run_phase2b_parallel(clusters: list[dict], extractions: list[dict]) -> list[dict]:
    """Run Phase 2b theme synthesis in parallel."""
    theme_results = []
    ref_offset = 0

    def synthesize_cluster(args):
        cluster, offset = args
        theme_name = cluster["theme"]
        indices = cluster["article_indices"]
        theme_extractions = [extractions[i] for i in indices if i < len(extractions)]
        if not theme_extractions:
            return None
        return synthesize_theme(theme_name, theme_extractions, offset)

    # Calculate offsets before parallelizing so ref numbers are predictable
    cluster_args = []
    for cluster in clusters:
        cluster_args.append((cluster, ref_offset))
        ref_offset += len(cluster["article_indices"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(synthesize_cluster, args) for args in cluster_args]
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            try:
                result = future.result()
                if result:
                    theme_results.append(result)
                    print(f"  ✓ Theme synthesized: {result.get('theme', '?')}")
            except Exception as e:
                print(f"  [theme] Thread error: {e}")

    return theme_results


# ---------------------------------------------------------------------------
# Phase 3: Write Big Picture from theme summaries
# ---------------------------------------------------------------------------

BIG_PICTURE_SYSTEM = """You are a senior intelligence analyst writing a concluding synthesis.
Write in direct, analytical prose. Return ONLY valid JSON, no markdown, no preamble."""

BIG_PICTURE_PROMPT = """Based on the following themed briefings from today's intelligence digest,
write a 2-3 paragraph "Big Picture" synthesis that connects the major threads.

Use inline superscript citations like [1] or [2,3] to reference specific sources where relevant.

Return this JSON:
{{
  "big_picture": "2-3 paragraphs connecting today's major themes, with inline citations..."
}}

Today's themed briefings:
{theme_summaries}"""


def synthesize_big_picture(theme_results: list[dict]) -> str:
    """Phase 3: Write Big Picture from theme summaries."""
    theme_summaries = "\n\n".join(
        f"THEME: {t.get('theme', '')}\n{t.get('briefing', '')[:500]}..."
        for t in theme_results
    )

    prompt = BIG_PICTURE_PROMPT.format(theme_summaries=theme_summaries)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=BIG_PICTURE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        return result.get("big_picture", "")
    except Exception as e:
        print(f"[summarizer] Phase 3 big picture failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_briefing(articles: list[dict], date: str) -> dict:
    """
    Full hierarchical pipeline:
      Phase 1  — parallel extraction from each article
      Phase 2a — cluster into themes
      Phase 2b — parallel synthesis per theme
      Phase 3  — big picture from theme summaries
    """

    # --- Phase 1 ---
    print(f"\n[summarizer] Phase 1: Extracting from {len(articles)} articles (parallel)...")
    for i, article in enumerate(articles):
        print(f"  [{i+1}/{len(articles)}] {article.get('source', '?')} — {article.get('title', '')[:60]}")

    extractions = run_phase1_parallel(articles)
    print(f"\n[summarizer] Phase 1 complete: {len(extractions)}/{len(articles)} extracted")

    if not extractions:
        return {
            "date": date,
            "error": "No articles could be extracted",
            "themes": [],
            "big_picture": "",
            "articles_processed": 0,
        }

    # --- Phase 2a ---
    print(f"\n[summarizer] Phase 2a: Clustering {len(extractions)} articles into themes...")
    clusters = cluster_extractions(extractions)

    # --- Phase 2b ---
    print(f"\n[summarizer] Phase 2b: Synthesizing {len(clusters)} themes (parallel)...")
    theme_results = run_phase2b_parallel(clusters, extractions)

    if not theme_results:
        return {
            "date": date,
            "error": "Theme synthesis failed",
            "themes": [],
            "big_picture": "",
            "articles_processed": len(extractions),
        }

    # --- Phase 3 ---
    print(f"\n[summarizer] Phase 3: Writing Big Picture...")
    big_picture = synthesize_big_picture(theme_results)

    print(f"[summarizer] Done. {len(theme_results)} themes generated.")

    return {
        "date": date,
        "themes": theme_results,
        "big_picture": big_picture,
        "articles_processed": len(extractions),
        "articles_attempted": len(articles),
        "publications": list(set(e.get("publication", "?") for e in extractions)),
    }