# Operations

## Local run

```bash
pip install -r requirements.txt
cp config/secrets.example.json config/secrets.json
# edit config/secrets.json and paste your Apify token
python scripts/run.py --verbose
open dist/index.html
```

For a zero-secret smoke test after cloning or moving machines:

```bash
python scripts/run.py --mock-data --verbose
open dist/index.html
```

## Secrets

`config/secrets.json` is gitignored. We never read system environment
variables; the Apify token must be in the file.

```jsonc
{
  "apify_token":          "apify_api_xxx",   // required
  "apify_actor":          "kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest",
  "apify_lookback_hours": 24,
  "github_token":         ""                 // optional, lifts GitHub Search rate limit
}
```

## CI / cron

[`.github/workflows/daily.yml`](../.github/workflows/daily.yml) runs every
3 hours on Asia/Shanghai segment boundaries and on manual dispatch. It:

1. Installs `requirements.txt`
2. Runs `pytest` (unit only — `integration` is skipped)
3. Materialises `config/secrets.json` from the repo secret `APIFY_TOKEN`
4. Computes the latest complete 3-hour Asia/Shanghai window
5. Builds `data/segments/YYYY-MM-DD/HH.json`
6. Merges complete days into `data/daily/YYYY-MM-DD.json`
7. Writes `data/index.json`, renders latest 24h, and copies `data/` into `dist/data/`
8. Commits JSON archive changes back to the repository
9. Uploads `dist/` as the Pages artifact and deploys it

[`.github/workflows/tests.yml`](../.github/workflows/tests.yml) runs the
unit tests on every push and PR.

[`.github/workflows/pages.yml`](../.github/workflows/pages.yml) deploys the
already-committed `data/` archive to GitHub Pages on every push to `main`.
It does not need `APIFY_TOKEN`; scheduled data fetching still belongs to
`daily.yml`.

## Custom domain

1. Settings → Pages → **Source: GitHub Actions**, **Custom domain:
   `ai.<domain>`**, **Enforce HTTPS**.
2. Create a repo-root `CNAME` file with the same value. `run.py` copies it
   into `dist/` so it survives every deploy.
3. Add a DNS record at your registrar: `CNAME  ai  <username>.github.io`.

The first deploy may take a few minutes for Let's Encrypt to issue the
cert.

## Tests

```bash
pytest                 # unit (offline, fast)
pytest -m integration  # live network — every RSS feed must be reachable
```

Mark new tests that hit the network with `@pytest.mark.integration` so
they don't run by default.

## Adding a source

1. Edit [`config/sources.json`](../config/sources.json).
2. Add a unit-test case in `tests/test_sources_config.py` if the change
   introduces a new top-level key.
3. Run `pytest -m integration` locally to verify the feed is alive.
4. Commit. CI will build the next digest.

## Debugging a failing run

- `python scripts/run.py --verbose` prints per-source progress and any
  network errors. Single-source failures are non-fatal.
- `pytest -m integration -k <feed-name>` checks a specific RSS feed.
- For trending: `python -c "import sys;sys.path.insert(0,'scripts');import fetch_github_trending as g;print(len(g.fetch_trending(['llm'])))"`.
- GitHub Pages deploy errors: check Actions → most recent run → `deploy`
  step.
- Segment debugging: `python scripts/segment_window.py` prints the latest
  complete 3-hour bucket; `python scripts/archive_data.py` rebuilds
  `data/index.json` and `dist/index.html` from committed JSON.

## Cost

- **Apify** — billed by returned data, with provider-specific minimums per
  actor call. The X fetcher batches all configured handles into one actor run
  per 3-hour segment, then clips the returned tweets per handle locally.
- **GitHub Actions** — free tier covers daily cron easily.
- **GitHub Pages** — free.
- **GitHub Search API** — free.
- **Domain** — whatever you pay your registrar.
