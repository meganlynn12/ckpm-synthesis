# CKPM Intel Brief

A twice-daily AI-curated news briefing PWA built on GitHub Pages. Pulls from open-source 
Substack/RSS feeds (OSINT) and premium journalism newsletters (PROPINT), synthesizes with 
Claude, and serves a clean mobile-first interface.

**Live:** `https://[your-github-username].github.io/ckpm-synthesis`

---

## Architecture

```
ckpm-synthesis/
├── .github/workflows/fetch.yml   # Scheduled GitHub Actions (6 AM & 6 PM ET)
├── scrapers/
│   ├── gmail.py                  # Substack + open-web Gmail ingestion
│   ├── rss.py                    # Free RSS fetcher
│   ├── substack.py               # Playwright-based Substack fetcher
│   └── premium_gmail.py          # Premium journalism Gmail ingestion (3-tier)
├── summarizer.py                 # OSINT Claude summarization + digest
├── summarizer_premium.py         # PROPINT three-tier synthesis pipeline
├── main.py                       # OSINT pipeline orchestrator
├── main_premium.py               # PROPINT pipeline orchestrator
├── config.py                     # Source definitions
├── output/
│   ├── content.json              # Current OSINT briefing
│   ├── premium_content.json      # Current PROPINT briefing
│   ├── archive.json              # OSINT archive index
│   ├── premium_archive.json      # PROPINT archive index
│   └── *.json                    # Dated archive files (scheduled runs only)
├── index.html                    # PWA frontend
├── sw.js                         # Service worker
├── manifest.json                 # PWA manifest
└── requirements.txt
```

---

## Two Pipelines

### OSINT — Substack & Open Web
Fetches from free RSS sources and Substack newsletters via Gmail. Synthesizes into 
a themed executive briefing with inline citations.

**Sources include:** Heather Cox Richardson, Nate Silver, The Bulwark, ProPublica, 
SCOTUSblog, Paul Krugman, Robert Reich, Scott Galloway, Sabato's Crystal Ball, 
Center for Humane Technology, and more.

### PROPINT — Premium Journalism
Ingests paid publication newsletters via Gmail across three tiers:

| Tier | Treatment | Sources |
|---|---|---|
| **Newsletter** | Structure extraction, rendered as-is | NYT, Economist, MIT TR, Foreign Affairs, Athletic, RAND |
| **Breaking** | End-of-day narrative digest (PM run only) | NYT Breaking News |
| **Longform** | Deep analytical synthesis | The Atlantic (features), David French (NYT) |

---

## GitHub Secrets Required

| Secret | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GMAIL_TOKEN` | OAuth token JSON for OSINT Gmail account (Substack newsletters) |
| `GMAIL_TOKEN_JSON_2` | OAuth token JSON for PROPINT Gmail account (premium newsletters) |

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
playwright install chromium --with-deps
```

### 2. Authorize Gmail accounts
Run once per account to generate OAuth tokens:
```bash
python authorize.py
```
A browser window opens — log into the target Gmail account and grant read access.
Copy the printed JSON into the corresponding GitHub secret.

- **Account 1** (`GMAIL_TOKEN`) — receives Substack newsletters + Sabato's Crystal Ball
- **Account 2** (`GMAIL_TOKEN_JSON_2`) — receives NYT, Economist, MIT TR, Atlantic, 
  Foreign Affairs, Athletic, RAND

### 3. Run locally
```bash
export ANTHROPIC_API_KEY=sk-ant-...
export GMAIL_TOKEN='{"token": ...}'
export GMAIL_TOKEN_JSON_2='{"token": ...}'
export GITHUB_EVENT_NAME=schedule   # omit to skip archiving

python main.py           # OSINT pipeline
python main_premium.py   # PROPINT pipeline
```

---

## Schedule

Runs twice daily via GitHub Actions:

| Run | UTC | ET (EDT) | ET (EST) |
|---|---|---|---|
| Morning | 10:00 | 6:00 AM | 5:00 AM |
| Evening | 22:00 | 6:00 PM | 5:00 PM |

Manual runs via **Actions → Fetch & Summarize Content → Run workflow** do not 
write archive files.

---

## Output Format

### OSINT — `output/content.json`
```json
{
  "date": "2026-05-20",
  "generated_at": "2026-05-20T10:00:00+00:00",
  "run_label": "6 AM",
  "big_picture": "Cross-cutting narrative...",
  "themes": [
    {
      "theme": "Theme title",
      "briefing": "Synthesis with inline citations [1,2]...",
      "publications": ["Source A", "Source B"],
      "references": [
        {"num": 1, "title": "Article", "url": "https://...", "publication": "Source A"}
      ]
    }
  ]
}
```

### PROPINT — `output/premium_content.json`
```json
{
  "date": "2026-05-20",
  "executive_summary": "Cross-cutting thread...",
  "newsletters": [
    {
      "source": "Foreign Affairs",
      "title": "Newsletter subject",
      "items": [{"headline": "...", "blurb": "...", "url": "https://..."}]
    }
  ],
  "breaking_digest": {
    "narrative": "End-of-day digest with citations [1]...",
    "references": [{"num": 1, "title": "Alert", "url": "https://..."}]
  },
  "longform": [
    {
      "source": "The Atlantic",
      "title": "Article title",
      "thesis": "Core argument...",
      "arguments": ["Key point 1", "Key point 2"],
      "significance": "Why it matters..."
    }
  ]
}
```

---

## PWA

The frontend is a mobile-first PWA installable from the GitHub Pages URL.
- Two-mode landing: **OSINT** and **PROPINT**
- Archive drawer with past briefings
- Citation tooltips on tap
- Dark mode support
- Updates automatically on each visit (service worker network-first for JSON)

---

## Adding New Sources

### OSINT RSS
Add to `FREE_RSS_SOURCES` in `config.py`:
```python
{"name": "Source Name", "url": "https://example.com/feed"},
```

### OSINT Gmail (non-Substack)
Update the query in `scrapers/gmail.py`:
```python
query = f"(from:@substack.com OR from:new@address.com) after:{cutoff_epoch_sec}"
```

### PROPINT Newsletter
Add to `PREMIUM_SENDERS` in `scrapers/premium_gmail.py`:
```python
"sender@domain.com": {
    "name": "Publication Name",
    "tier": "newsletter",   # or "longform" or "breaking"
    "home_url": "https://www.domain.com",
},
```
And add to `SOURCE_URLS` in `index.html`.

### Atlantic-style split (newsletter + longform from same sender)
Add subject keywords to `ATLANTIC_NEWSLETTER_SUBJECTS` in `premium_gmail.py`.

### David French-style detection (longform by sender name)
Add a condition to `_detect_tier()` in `premium_gmail.py`.