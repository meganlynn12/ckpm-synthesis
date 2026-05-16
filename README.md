# Content Aggregator — Phase 1

Nightly pipeline that fetches, summarizes, and digests articles from Substack 
and free RSS sources using Claude AI.

## Project Structure

```
content-aggregator/
├── .github/workflows/fetch.yml   # Scheduled GitHub Action
├── scrapers/
│   ├── substack.py               # Playwright-based Substack fetcher
│   └── rss.py                    # Free RSS fetcher
├── summarizer.py                 # Claude summarization + digest
├── main.py                       # Pipeline orchestrator
├── config.py                     # All source definitions
├── output/
│   └── content.json              # Generated output (committed nightly)
├── sessions/                     # Auth sessions (gitignored)
└── requirements.txt
```

## GitHub Secrets Required

Go to your repo → Settings → Secrets and variables → Actions → New repository secret

| Secret | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `SUBSTACK_EMAIL` | Your Substack login email |
| `SUBSTACK_PASSWORD` | Your Substack password |

## Setup

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium --with-deps

# Set environment variables locally for testing
export ANTHROPIC_API_KEY=sk-ant-...
export SUBSTACK_EMAIL=you@email.com
export SUBSTACK_PASSWORD=yourpassword

# Run
python main.py
```

## Verifying Substack Slugs

A few slugs in `config.py` are marked `# TODO: verify`. To confirm:
1. Go to the publication's Substack URL
2. The slug is the subdomain: `https://{slug}.substack.com`
3. Update `config.py` if different

## Output Format

`output/content.json`:
```json
{
  "generated_at": "2025-01-15T11:00:00+00:00",
  "elapsed_seconds": 45.2,
  "article_count": 47,
  "digest": "Today's big picture: ...",
  "articles": [
    {
      "source": "Letters from an American",
      "title": "Article title",
      "url": "https://...",
      "published": "Wed, 15 Jan 2025 ...",
      "summarized": true,
      "bullets": ["Point 1", "Point 2", "Point 3"],
      "themes": ["democracy", "2024 election"],
      "relevance": 8
    }
  ]
}
```

## Schedule

Runs daily at **6:00 AM ET** via GitHub Actions cron.
Trigger manually via Actions → "Fetch & Summarize Content" → Run workflow.

## Phase Roadmap

- **Phase 1** ✅ Substack + free RSS + Claude summarization
- **Phase 2** — Gmail API ingestion (NYT, Atlantic, MIT TR newsletters)
- **Phase 3** — Playwright scrapers for WSJ, Economist, Financial Times, Foreign Affairs
- **Phase 4** — PWA frontend on GitHub Pages
