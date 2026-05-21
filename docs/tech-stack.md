# Tech Stack

## Runtime

- **Python 3.11+** — `from __future__ import annotations`, structural
  pattern matching used sparingly.
- No virtualenv requirement at runtime; CI installs into the job's
  ephemeral Python.

## Libraries

| Library      | What for                                         |
| ------------ | ------------------------------------------------ |
| `requests`   | All HTTP (Apify, GitHub Search API)              |
| `feedparser` | RSS / Atom parsing                               |
| `dateutil`   | Permissive date parsing                          |
| `pytest`     | Tests                                            |

That's it. No web framework, no database, no JS toolchain.

## Output

- A single `dist/index.html` (~15–60 KB depending on item count) with
  inline CSS and inline SVG. No external assets.
- If a repo-root `CNAME` exists, a `dist/CNAME` file copied from it for
  GitHub Pages custom-domain binding.

## Infrastructure

- **GitHub Actions** — 3-hour cron, push deploy, and manual
  `workflow_dispatch`. Three workflows live in `.github/workflows/`:
  - `daily.yml`: runs the pipeline, deploys `dist/` to Pages.
  - `pages.yml`: deploys already-committed `data/` to Pages on push.
  - `tests.yml`: runs `pytest` on push and PR.
- **GitHub Pages** — static hosting, `Source: GitHub Actions`.
- **Custom domain** — `ai.<your-domain>` via the repo-root `CNAME` file
  + a DNS CNAME record. Let's Encrypt cert is auto-issued by Pages.

## Secrets

`config/secrets.json` is **gitignored**. Schema:

```jsonc
{
  "apify_token":          "apify_api_xxx",   // required
  "apify_actor":          "kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest",
  "apify_lookback_hours": 24,
  "github_token":         ""                 // optional, raises Search API rate limit
}
```

In CI, the workflow generates this file on the fly from the `APIFY_TOKEN`
(and optionally `GH_TRENDING_TOKEN`) repository secret.

## Why these choices

- **Apify over the X API or scraping**: cheapest stable option with
  rotating proxies and a maintained actor.
- **Search API over GitHub trending RSS scrapers**: official and
  topic-filterable; no third-party drift.
- **`feedparser` over a homemade XML walker**: handles RSS 2.0, Atom,
  and a long tail of malformed feeds.
- **Static HTML over a SPA**: fastest to load, archivable, indexable,
  and survives the next decade of JS framework churn unchanged.
