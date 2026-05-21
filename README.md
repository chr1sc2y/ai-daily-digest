# AI Daily Digest

A self-hosted, zero-server daily digest of what AI's leaders are saying — across X posts, blogs, podcasts, GitHub trending, and YouTube.

```
GitHub Actions (cron) ──▶ Apify (X) + RSS + GitHub Search ──▶ dist/index.html ──▶ GitHub Pages
```

## Run locally

```bash
pip install -r requirements.txt
cp config/secrets.example.json config/secrets.json
# paste your Apify token into config/secrets.json
python scripts/run.py --verbose
open dist/index.html
```

Smoke-test the full renderer without network calls or secrets:

```bash
python scripts/run.py --mock-data --output dist/index.html
open dist/index.html
```

Write a dated normalized data snapshot while building:

```bash
python scripts/run.py --output dist/index.html --data-output data/$(date +%F).json
```

## Deploy

Push to GitHub, then:

1. **Settings → Secrets → Actions**: add `APIFY_TOKEN`.
2. **Settings → Pages**: source = *GitHub Actions*.
3. Optional custom domain: create a repo-root `CNAME` with `ai.<your-domain>`, add DNS `CNAME ai <username>.github.io`, then enable HTTPS in Pages.
4. **Actions → Daily Digest → Run workflow** for the first build.

## Tests

```bash
pytest                  # unit tests, offline
pytest -m integration   # live RSS reachability
```

## Docs

See [`docs/`](docs/README.md) — architecture, modules, data sources, tech stack, operations.

## License

MIT.

Inspired by [zarazhangrui/follow-builders](https://github.com/zarazhangrui/follow-builders).
