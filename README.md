# Firsthand AI Digest

**Every 3 hours, the sharpest AI voices in one place.**

A self-hosted digest that automatically aggregates what AI's leading researchers, founders, and builders are saying — across X posts, long-form blogs, podcasts, GitHub trending repos, and YouTube — then publishes it as a clean, interactive site on GitHub Pages.

No login. No algorithm. No noise.

---

## What it tracks

| Source | What you get |
|--------|-------------|
| **X / Twitter** | Real-time posts from 50+ AI leaders |
| **Blogs** | Long-form writing from OpenAI, Anthropic, DeepMind, and independent researchers |
| **Podcasts** | Episodes featuring leaders you follow, filtered by name |
| **GitHub Trending** | High-momentum AI repos, refreshed every 3 hours |
| **YouTube** | Recent uploads from AI research channels |

---

## How it works

GitHub Actions fetches from every source on a 3-hour schedule and commits normalized data segments to this repo. GitHub Pages serves the static site — no backend, no database, no cost.

Flip between time windows (3h · 6h · 12h · 24h · 3d · 7d) to see what's fresh or catch up on the week.

---

## Quick start

```bash
pip install -r requirements.txt
python scripts/run.py --mock-data --output dist/index.html
open dist/index.html
```

To deploy your own instance, see **[docs/operations.md](docs/operations.md)**.

---

## Docs

Full engineering reference: **[docs/](docs/README.md)**

---

## License

MIT · Inspired by [zarazhangrui/follow-builders](https://github.com/zarazhangrui/follow-builders)
