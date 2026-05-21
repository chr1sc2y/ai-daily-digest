# Architecture

## Goal

Produce, every 24 hours, a single self-contained `index.html` that summarises
what the leaders of the AI industry are saying — across X posts, blogs,
podcasts, GitHub trending, and YouTube — and serve it from a custom domain
with zero servers to maintain.

## Topology

```
                ┌─────────────────────────────────────┐
                │      GitHub Actions (cron, 01:00 UTC) │
                └────────────────┬────────────────────┘
                                 │
                ┌────────────────┴────────────────┐
                │       scripts/run.py            │
                └─┬─────┬─────┬─────┬──────┬──────┘
                  │     │     │     │      │
        ┌─────────┘     │     │     │      └────────┐
        ▼               ▼     ▼     ▼               ▼
  Apify Actor       RSS feeds  RSS    GitHub      RSS feeds
  (X scraper)        (blogs)  (podc.) Search API  (YouTube)
        │               │     │     │               │
        └─────┬─────────┴─────┴─────┴───────────────┘
              │
              ▼
       window-filter → cross-category dedup → sort
              │
              ├──▶ data/YYYY-MM-DD.json ───▶ commit to repo
              │
              ▼
        render → dist/index.html ───▶ GitHub Pages ───▶ ai.<domain>
```

## Pipeline (run.py)

| # | Stage              | Module                     | Notes                                  |
|---|--------------------|----------------------------|----------------------------------------|
| 1 | Fetch X posts      | `fetch_x.py`               | Apify kaitoeasyapi actor               |
| 2 | Fetch blogs        | `fetch_rss.py`             | Atom / RSS via `feedparser`            |
| 3 | Fetch trending     | `fetch_github_trending.py` | GitHub Search API, topic + stars       |
| 4 | Fetch YouTube      | `fetch_rss.py`             | `videos.xml?channel_id=…`              |
| 5 | Fetch podcasts     | `fetch_podcasts.py`        | RSS + leader-name keyword filter       |
| 6 | Window-filter      | `run.py`                   | per-category cutoff (hours)            |
| 7 | Cross-cat dedup    | `fetch_rss.dedup`          | canonical URL (strip utm, lowercase)   |
| 8 | Sort + clip        | `run.py`                   | newest first, max-per-source           |
| 9 | Data snapshot      | `run.py`                   | normalized `data/YYYY-MM-DD.json`      |
|10 | Render             | `render_html.py`           | self-contained HTML, no external CSS   |

## Failure model

- Any single source failure (network, parse error, rate limit) is logged
  and the rest of the pipeline continues. We never abort the whole run for
  one feed.
- Re-runs are idempotent: the next cron tick simply rebuilds `dist/`.
- No persistent state is read between runs — the only output is the static
  HTML.

## Why static + GitHub Pages

- Free hosting, zero servers.
- Custom subdomain via `CNAME` with auto-issued Let's Encrypt cert.
- Public artifacts make the digest archivable / forkable.
- Build runs in CI so secrets never touch the user's machine.

## Future hooks

- LLM summarisation: a `summarize.py` step can be inserted between dedup
  and render. The render layer already accepts a `summary` field per item.
- Multiple issues per day: the `--hours` flag and the cron schedule are
  the only knobs needed.
