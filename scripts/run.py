"""Entry point for the AI Daily Digest pipeline.

Usage:
    python scripts/run.py [--output dist/index.html] [--max-per-source 5] [--hours 24]

Pipeline (stable order, see docs/architecture.md):
    1. Fetch X posts via Apify
    2. Fetch generic RSS feeds: blogs, GitHub releases, YouTube channels
    3. Fetch podcasts (RSS + leader keyword filter)
    4. Apply per-category time-window filter
    5. Dedup by canonical URL across categories
    6. Sort by published desc and clip to max-per-source
    7. Render to a single self-contained HTML
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running both as `python scripts/run.py` and as a module.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import fetch_github_trending  # noqa: E402
import fetch_podcasts  # noqa: E402
import fetch_rss  # noqa: E402
import fetch_x  # noqa: E402
import render_html  # noqa: E402

ROOT = HERE.parent
DEFAULT_CONFIG = ROOT / "config" / "sources.json"
DEFAULT_OUTPUT = ROOT / "dist" / "index.html"

log = logging.getLogger("ai-daily-digest")


def _within_window(item: dict, cutoff: datetime) -> bool:
    pub = item.get("published")
    if pub is None:
        # Keep undated items so we don't accidentally drop everything.
        return True
    return pub >= cutoff


def _within_range(item: dict, start: datetime, end: datetime) -> bool:
    pub = item.get("published")
    if pub is None:
        return True
    return start <= pub < end


def _parse_utc_datetime(raw: str) -> datetime:
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _sort_desc(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda i: i.get("published") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


def _jsonable_item(item: dict) -> dict:
    out = dict(item)
    published = out.get("published")
    if isinstance(published, datetime):
        out["published"] = published.astimezone(timezone.utc).isoformat()
    return out


def _data_payload(
    *,
    generated_at: datetime,
    x_items: list[dict],
    blog_items: list[dict],
    podcast_items: list[dict],
    release_items: list[dict],
    video_items: list[dict],
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> dict:
    payload = {
        "schema_version": 1,
        "generated_at": generated_at.astimezone(timezone.utc).isoformat(),
        "counts": {
            "x": len(x_items),
            "blogs": len(blog_items),
            "podcasts": len(podcast_items),
            "releases": len(release_items),
            "videos": len(video_items),
        },
        "items": {
            "x": [_jsonable_item(i) for i in x_items],
            "blogs": [_jsonable_item(i) for i in blog_items],
            "podcasts": [_jsonable_item(i) for i in podcast_items],
            "releases": [_jsonable_item(i) for i in release_items],
            "videos": [_jsonable_item(i) for i in video_items],
        },
    }
    if window_start and window_end:
        payload["window"] = {
            "start": window_start.astimezone(timezone.utc).isoformat(),
            "end": window_end.astimezone(timezone.utc).isoformat(),
        }
    return payload


def _mock_items(now: datetime) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    """Deterministic-ish sample payload for local smoke tests and screenshots."""

    def item(kind: str, source: str, title: str, summary: str, link: str, hours_ago: int,
             role: str = "", handle: str = "", author: str = "") -> dict:
        return {
            "kind": kind,
            "source_name": source,
            "source_role": role,
            "source_handle": handle or source,
            "title": title,
            "summary": summary,
            "link": link,
            "author": author or source,
            "published": now - timedelta(hours=hours_ago),
        }

    x_items = [
        item(
            "x",
            "Sam Altman",
            "Shipping note",
            "We are seeing agents move from demos into real daily workflows. The next step is reliability, not flash.",
            "https://x.com/sama/status/mock-1",
            2,
            role="CEO, OpenAI",
            handle="sama",
            author="sama",
        ),
        item(
            "x",
            "Andrej Karpathy",
            "LLM tooling",
            "Small, understandable evals remain the fastest way to make model-powered products less mysterious.",
            "https://x.com/karpathy/status/mock-2",
            5,
            role="Eureka Labs / ex-OpenAI, Tesla",
            handle="karpathy",
            author="karpathy",
        ),
    ]
    blog_items = [
        item(
            "blog",
            "OpenAI Blog",
            "Building reliable agentic systems",
            "A practical look at tool use, handoffs, and measuring model behavior before broad release.",
            "https://openai.com/blog/mock-agentic-systems",
            12,
            role="By OpenAI",
        ),
        item(
            "blog",
            "Simon Willison",
            "Notes on prompt injection and product boundaries",
            "A field note on isolating untrusted text and keeping user intent explicit in AI applications.",
            "https://simonwillison.net/mock/prompt-injection",
            36,
            role="By Simon Willison",
        ),
    ]
    podcast_items = [
        item(
            "podcast",
            "Latent Space",
            "Sam Altman on agents in production",
            "A conversation about product pressure, evaluation loops, and the long tail of model behavior.",
            "https://www.latent.space/p/mock-agents",
            72,
            role="Featuring Sam Altman",
        )
    ]
    release_items = [
        item(
            "release",
            "example/agent-runtime",
            "A compact runtime for AI agent workflows",
            "12,480 stars · Tools for tracing, retrying, and inspecting multi-step agent runs.",
            "https://github.com/example/agent-runtime",
            18,
            role="example/agent-runtime",
            author="example",
        )
    ]
    video_items = [
        item(
            "video",
            "Google DeepMind",
            "Research update: reasoning models",
            "A short briefing on recent reasoning-model experiments and benchmark behavior.",
            "https://www.youtube.com/watch?v=mock-video",
            20,
            role="Channel · Google DeepMind",
        )
    ]
    return x_items, blog_items, release_items, video_items, podcast_items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the AI daily digest HTML.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-per-source", type=int, default=5)
    parser.add_argument("--hours", type=int, default=24,
                        help="Window for X posts.")
    parser.add_argument("--blog-hours", type=int, default=24 * 7,
                        help="Window for blog posts (default 7 days).")
    parser.add_argument("--release-hours", type=int, default=24 * 7,
                        help="Window for GitHub releases (default 7 days).")
    parser.add_argument("--video-hours", type=int, default=24 * 7,
                        help="Window for YouTube videos (default 7 days).")
    parser.add_argument("--podcast-hours", type=int, default=24 * 30,
                        help="Window for podcast episodes (default 30 days).")
    parser.add_argument("--no-podcast-filter", action="store_true",
                        help="Keep all podcast episodes (don't filter by leader name).")
    parser.add_argument("--mock-data", action="store_true",
                        help="Render built-in sample data without network calls or secrets.")
    parser.add_argument("--data-output", type=Path,
                        help="Optional JSON path for the normalized digest data.")
    parser.add_argument("--window-start",
                        help="UTC ISO timestamp for an inclusive global data window start.")
    parser.add_argument("--window-end",
                        help="UTC ISO timestamp for an exclusive global data window end.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(levelname)s] %(name)s: %(message)s",
    )

    if not args.config.exists():
        log.error("Config not found: %s", args.config)
        return 2

    config = json.loads(args.config.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    window_start = _parse_utc_datetime(args.window_start) if args.window_start else None
    window_end = _parse_utc_datetime(args.window_end) if args.window_end else None
    if (window_start is None) != (window_end is None):
        log.error("--window-start and --window-end must be provided together.")
        return 2
    if window_start and window_end and window_start >= window_end:
        log.error("--window-start must be before --window-end.")
        return 2

    if args.mock_data:
        log.info("Mock: rendering built-in sample data; no network calls.")
        x_items, blog_items, release_items, video_items, podcast_items = _mock_items(now)
    else:
        # ---- 1. X posts -------------------------------------------------------
        log.info("X: fetching for %d users...", len(config.get("x_users", [])))
        x_items = fetch_x.fetch_all(
            users=config.get("x_users", []),
            max_items=args.max_per_source,
        )

        # ---- 2. Blogs / Releases / YouTube (generic RSS) ----------------------
        log.info("Blogs: fetching %d feeds...", len(config.get("blogs", [])))
        blog_items = fetch_rss.fetch_many(
            config.get("blogs", []),
            kind="blog",
            max_items=args.max_per_source,
            role_template="By {publisher}",
        )

        log.info("Releases: fetching trending AI repos...")
        trending_cfg = config.get("github_trending", {}) or {}
        release_items = fetch_github_trending.fetch_trending(
            topics=trending_cfg.get("topics"),
            min_stars=trending_cfg.get("min_stars", 1000),
            lookback_days=trending_cfg.get("lookback_days", 14),
            max_repos=trending_cfg.get("max_repos", 20),
        )

        log.info("YouTube: fetching %d channels...", len(config.get("youtube", [])))
        video_items = fetch_rss.fetch_many(
            config.get("youtube", []),
            kind="video",
            max_items=args.max_per_source,
            role_template="Channel · {channel}",
        )

        # ---- 3. Podcasts (RSS + leader filter) --------------------------------
        log.info("Podcasts: fetching %d feeds...", len(config.get("podcasts", [])))
        podcast_items = fetch_podcasts.fetch_all(
            podcasts=config.get("podcasts", []),
            leaders=config.get("x_users", []),
            max_items=args.max_per_source,
            require_leader_match=not args.no_podcast_filter,
        )

    # ---- 4. Time-window filter --------------------------------------------
    if window_start and window_end:
        x_items       = [i for i in x_items       if _within_range(i, window_start, window_end)]
        blog_items    = [i for i in blog_items    if _within_range(i, window_start, window_end)]
        release_items = [i for i in release_items if _within_range(i, window_start, window_end)]
        video_items   = [i for i in video_items   if _within_range(i, window_start, window_end)]
        podcast_items = [i for i in podcast_items if _within_range(i, window_start, window_end)]
    else:
        x_items       = [i for i in x_items       if _within_window(i, now - timedelta(hours=args.hours))]
        blog_items    = [i for i in blog_items    if _within_window(i, now - timedelta(hours=args.blog_hours))]
        release_items = [i for i in release_items if _within_window(i, now - timedelta(hours=args.release_hours))]
        video_items   = [i for i in video_items   if _within_window(i, now - timedelta(hours=args.video_hours))]
        podcast_items = [i for i in podcast_items if _within_window(i, now - timedelta(hours=args.podcast_hours))]

    # ---- 5. Dedup by canonical URL (cross-category) -----------------------
    # X items are kept untouched (handles can quote-tweet links from other
    # categories; we want to see both the tweet and the underlying post).
    deduped = fetch_rss.dedup(blog_items + release_items + video_items + podcast_items)
    blog_items    = [i for i in deduped if i["kind"] == "blog"]
    release_items = [i for i in deduped if i["kind"] == "release"]
    video_items   = [i for i in deduped if i["kind"] == "video"]
    podcast_items = [i for i in deduped if i["kind"] == "podcast"]

    # ---- 6. Sort and render -----------------------------------------------
    x_items, blog_items, release_items, video_items, podcast_items = (
        _sort_desc(x_items),
        _sort_desc(blog_items),
        _sort_desc(release_items),
        _sort_desc(video_items),
        _sort_desc(podcast_items),
    )

    log.info(
        "Render: %d posts, %d blogs, %d podcasts, %d releases, %d videos",
        len(x_items), len(blog_items), len(podcast_items),
        len(release_items), len(video_items),
    )

    if args.data_output:
        payload = _data_payload(
            generated_at=now,
            x_items=x_items,
            blog_items=blog_items,
            podcast_items=podcast_items,
            release_items=release_items,
            video_items=video_items,
            window_start=window_start,
            window_end=window_end,
        )
        args.data_output.parent.mkdir(parents=True, exist_ok=True)
        args.data_output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        log.info("Wrote data %s", args.data_output)

    html_text = render_html.render(
        x_items=x_items,
        podcast_items=podcast_items,
        blog_items=blog_items,
        release_items=release_items,
        video_items=video_items,
        site=config.get("site") or {},
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_text, encoding="utf-8")
    log.info("Wrote %s", args.output)

    # If a CNAME file exists at the repo root (used by GitHub Pages to bind a
    # custom domain), copy it next to the generated HTML so it survives the
    # Pages deployment.
    cname = ROOT / "CNAME"
    output_cname = args.output.parent / "CNAME"
    if cname.exists():
        shutil.copy2(cname, output_cname)
        log.info("Copied CNAME to %s", output_cname)
    elif output_cname.exists():
        output_cname.unlink()
        log.info("Removed stale CNAME from %s", output_cname)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
