# Data Sources

What we fetch, where it lives, and how stable it is.

## X / Twitter

- **Provider**: Apify actor [`kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest`](
  https://apify.com/kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest)
- **Cost**: ~$0.25 per 1k tweets; each 3-hour run batches all handles into
  one actor call and then clips locally.
- **Input mode**: one batched Apify Actor run with `searchTerms[]`, using
  Twitter search syntax like `from:sama since_time:<unix> until_time:<unix>`.
- **Stability**: backed by Apify's rotating proxy pool; survives X's
  anti-scraping changes better than a direct API.
- **Auth**: `apify_token` in `config/secrets.json`.
- **Why not the official X API**: free tier is too restrictive; paid tier
  is $100+/mo for our volume.
- **Why not RapidAPI's twitter154**: that endpoint went dark.

The configured handles live in [`config/sources.json`](../config/sources.json)
under `x_users[]`.

## Blogs

Plain RSS / Atom feeds. Currently:

| Source                | Feed                                                   |
| --------------------- | ------------------------------------------------------ |
| OpenAI                | `https://openai.com/blog/rss.xml`                      |
| Google DeepMind       | `https://deepmind.google/blog/rss.xml`                 |
| Sam Altman            | `https://blog.samaltman.com/posts.atom`                |
| Andrej Karpathy       | `https://karpathy.github.io/feed.xml`                  |
| Simon Willison        | `https://simonwillison.net/atom/everything/`           |
| Lilian Weng           | `https://lilianweng.github.io/index.xml`               |
| Import AI (Jack Clark)| `https://jack-clark.net/feed/`                         |

Anthropic's and Meta's blog feeds are intentionally absent — Anthropic's
`/news/rss.xml` and `/engineering/rss.xml` both return 404, and Meta has
no public RSS. Anthropic-side signal is captured via the Anthropic
YouTube channel and `@DarioAmodei` / `@AmandaAskell` / `@_catwu` on X.

## Podcasts

Public RSS feeds, hosted on whatever each show happens to use (Substack,
Megaphone, Libsyn, the host's own server). We do not depend on a single
aggregator (Spotify / Apple) because none of them re-export third-party
shows as RSS.

Episode-level filtering: only keep episodes whose title / summary /
author / keywords match a configured X leader's name or `@handle`. Pass
`--no-podcast-filter` to disable.

| Source                                  | Notes                              |
| --------------------------------------- | ---------------------------------- |
| Latent Space                            | Substack                           |
| Training Data (Sequoia)                 | Megaphone                          |
| No Priors                               | Megaphone                          |
| Unsupervised Learning (Redpoint)        | Simplecast                         |
| The MAD Podcast with Matt Turck         | Anchor                             |
| AI & I (Every / Dan Shipper)            | Transistor                         |

## GitHub Trending

GitHub does not publish an official trending RSS, so we proxy it with
the [Search API](https://docs.github.com/rest/search/search#search-repositories):

```
GET /search/repositories?q=topic:<t>+stars:>=N+pushed:>=YYYY-MM-DD&sort=stars
```

Run once per topic; merge results by `full_name`; cap at `max_repos`.

Defaults (see [`config/sources.json`](../config/sources.json) →
`github_trending`):

- topics: `llm`, `ai-agents`, `generative-ai`, `agentic-ai`, `rag`,
  `transformers`, `vector-database`
- `min_stars`: 2000
- `lookback_days`: 14
- `max_repos`: 20

Rate limit: 10 req/min unauthenticated, 30/min with a token. Drop a
`github_token` (any classic PAT, no scopes needed) into
`config/secrets.json` if you ever hit a 403.

## YouTube

YouTube exposes a free per-channel Atom feed at:

```
https://www.youtube.com/feeds/videos.xml?channel_id=UC...
```

To find a channel ID: visit the channel page, view source, search for
`"channelId":"UC...`. The current list:

| Channel              | Type                       |
| -------------------- | -------------------------- |
| Lex Fridman          | host                       |
| Dwarkesh Patel       | host                       |
| Two Minute Papers    | research roundup           |
| Yannic Kilcher       | paper deep dives           |
| AI Explained         | analysis                   |
| OpenAI               | first-party (demos, keynotes) |
| Google DeepMind      | first-party (research)     |
| Anthropic            | first-party (research)     |
| Hugging Face         | first-party (tools, models)|

## Frequency / Window defaults

| Category | Cron | Window |
|----------|------|--------|
| X / posts        | every 3 h | exact 3 h segment |
| Blogs            | every 3 h | exact 3 h segment |
| Trending repos   | every 3 h | exact 3 h segment |
| YouTube videos   | every 3 h | exact 3 h segment |
| Podcasts         | every 3 h | exact 3 h segment |

Knobs: `--hours`, `--blog-hours`, `--release-hours`, `--video-hours`,
`--podcast-hours`.
