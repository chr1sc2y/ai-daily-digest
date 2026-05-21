# Modules

A one-page reference for each file under `scripts/` and `tests/`.

## `scripts/run.py`

The pipeline entry point. Reads `config/sources.json`, orchestrates the
five fetchers, applies per-category time windows, dedups across
categories, sorts, and writes `dist/index.html` (plus `CNAME` if present).

CLI flags:

| Flag                  | Default | Meaning                                      |
| --------------------- | ------- | -------------------------------------------- |
| `--config`            | `config/sources.json` | sources file path             |
| `--output`            | `dist/index.html`     | output path                   |
| `--max-per-source`    | 5       | items kept per handle / feed                 |
| `--hours`             | 24      | window for X posts                           |
| `--blog-hours`        | 168     | window for blogs (7 d)                       |
| `--release-hours`     | 168     | window for trending repos (7 d)              |
| `--video-hours`       | 168     | window for YouTube (7 d)                     |
| `--podcast-hours`     | 720     | window for podcasts (30 d)                   |
| `--no-podcast-filter` |         | keep all episodes regardless of leader name  |
| `--data-output`       |         | optional normalized JSON output path         |
| `--verbose`           |         | DEBUG logging                                |

## `scripts/fetch_x.py`

Apify [`kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest`](
https://apify.com/kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest)
actor. Reads `apify_token`, `apify_actor`, `apify_lookback_hours` from
`config/secrets.json`. Never reads system environment variables on
purpose — secrets must live in the file. The CI workflow generates that
file from the `APIFY_TOKEN` repo secret.

## `scripts/fetch_rss.py`

Generic RSS / Atom helpers used by blogs, podcasts (delegated), and
YouTube.

- `fetch_feed(url)` — single feed → list of normalized item dicts.
- `fetch_many(feeds, kind, max_items, role_template)` — batch fetch and
  tag each item with its `kind`.
- `canonical_url(url)` — lowercase host, strip `utm_*`, drop trailing
  slash. Used by `dedup`.
- `dedup(items)` — keep the first occurrence per canonical link.

## `scripts/fetch_podcasts.py`

Thin wrapper around `fetch_rss._fetch_feed` that adds a leader-name
keyword filter (`require_leader_match=True` by default). An episode is
kept if its title / summary / author / keywords mention the full name,
last name, or `@handle` of any configured X leader.

## `scripts/fetch_github_trending.py`

GitHub has no official trending RSS; we proxy it via the public
Search API (`/search/repositories`). The config block is:

```jsonc
"github_trending": {
  "topics":        ["llm", "ai-agents", "generative-ai", ...],
  "min_stars":     2000,
  "lookback_days": 14,
  "max_repos":     20
}
```

One Search call per topic, results merged by `full_name` (highest star
count wins), sorted by stars desc, capped at `max_repos`. Unauth
requests are limited to ~10 req/min — set `github_token` in
`config/secrets.json` to lift it.

## `scripts/render_html.py`

Pure-Python HTML renderer. Produces a single file with inline CSS and
no external assets. Editorial / magazine layout: serif display headings,
mono-spaced metadata, sticky topbar, sticky section nav, 1-px hairline
grid of cards.

`render(x_items, podcast_items, blog_items, release_items, video_items)`
returns the full HTML document. Every item must have at least
`source_name`, `summary`, `link`, `published`, `kind`.

## Tests

| File                                  | Scope                                                           |
| ------------------------------------- | --------------------------------------------------------------- |
| `tests/test_parse_date.py`            | Date parsing helpers                                            |
| `tests/test_fetch_x.py`               | Apify client, mocked HTTP                                       |
| `tests/test_fetch_rss.py`             | Generic RSS / canonical / dedup                                 |
| `tests/test_fetch_podcasts.py`        | Leader-name filter                                              |
| `tests/test_fetch_github_trending.py` | Search-API client, mocked HTTP                                  |
| `tests/test_sources_config.py`        | `config/sources.json` shape, no duplicates                      |
| `tests/test_podcast_rss_integration.py` | Live network — every feed reachable (`pytest -m integration`) |

`pytest.ini` skips `integration` by default.
