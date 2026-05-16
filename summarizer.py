# summarizer.py
# Sends each article to Claude for summarization.
# Produces bullet-point summaries and theme tags.
# Also generates a daily digest across all articles.

import asyncio
import json
import os
from anthropic import AsyncAnthropic

client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# How many articles to summarize in parallel (stay well within rate limits)
CONCURRENCY = 5

ARTICLE_PROMPT = """\
You are a research assistant summarizing articles for a well-informed reader \
interested in politics, economics, law, technology, and current events.

Article source: {source}
Article title: {title}
Article content:
{content}

Respond with ONLY valid JSON in this exact format (no markdown, no extra text):
{{
  "bullets": [
    "First key point in one clear sentence",
    "Second key point in one clear sentence",
    "Third key point in one clear sentence"
  ],
  "themes": ["theme1", "theme2", "theme3"],
  "relevance": 8
}}

Guidelines:
- bullets: exactly 3 bullet points, each a complete sentence capturing a distinct key idea
- themes: 2-4 short lowercase tags (e.g. "supreme court", "inflation", "2024 election", "ai policy")
- relevance: integer 1-10 rating how significant/substantive this article is (10 = major news/analysis)
"""

DIGEST_PROMPT = """\
You are synthesizing today's reading list for a well-informed reader.
Below are summaries of {count} articles from across politics, economics, law, \
technology, and current events.

Articles:
{articles}

Write a daily digest with:
1. A 2-3 sentence "Big Picture" paragraph identifying the most important overarching \
   themes across today's reading
2. A "Top Stories" section listing the 5 most significant articles with one sentence each \
   explaining why they matter
3. A "Connections" section (2-3 sentences) noting any interesting patterns, contradictions, \
   or through-lines across sources

Be analytical and direct. Do not hedge. Assume the reader is sophisticated.
"""


async def summarize_article(article: dict, semaphore: asyncio.Semaphore) -> dict:
    """Call Claude to summarize a single article. Returns the article with fields filled in."""
    async with semaphore:
        try:
            prompt = ARTICLE_PROMPT.format(
                source=article["source"],
                title=article["title"],
                content=article["content"],
            )
            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            parsed = json.loads(raw)

            article["bullets"] = parsed.get("bullets", [])
            article["themes"] = parsed.get("themes", [])
            article["relevance"] = parsed.get("relevance", 5)
            article["summarized"] = True

        except json.JSONDecodeError as e:
            print(f"    ⚠ JSON parse error for '{article['title']}': {e}")
            article["summarized"] = False
        except Exception as e:
            print(f"    ✗ Summarization error for '{article['title']}': {e}")
            article["summarized"] = False

        return article


async def generate_digest(articles: list[dict]) -> str:
    """Generate a daily digest from all summarized articles."""
    summarized = [a for a in articles if a.get("summarized")]
    if not summarized:
        return "No articles were successfully summarized today."

    # Build compact article list for the digest prompt
    article_list = "\n\n".join(
        f"[{a['source']}] {a['title']}\n" + "\n".join(f"- {b}" for b in a.get("bullets", []))
        for a in summarized
    )

    prompt = DIGEST_PROMPT.format(count=len(summarized), articles=article_list)

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"  ✗ Digest generation failed: {e}")
        return "Digest generation failed."


async def summarize_articles(articles: list[dict]) -> tuple[list[dict], str]:
    """
    Summarize all articles concurrently, then generate a daily digest.
    Returns (summarized_articles, digest_text).
    """
    print(f"  Summarizing {len(articles)} articles (concurrency={CONCURRENCY})...")
    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [summarize_article(article, semaphore) for article in articles]
    summarized = await asyncio.gather(*tasks)

    success = sum(1 for a in summarized if a.get("summarized"))
    print(f"  ✓ {success}/{len(summarized)} articles summarized")

    print("  Generating daily digest...")
    digest = await generate_digest(list(summarized))

    return list(summarized), digest
