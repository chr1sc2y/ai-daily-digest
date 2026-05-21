"""Live-network integration tests covering every RSS feed in sources.json.

Run only when explicitly requested::

    pytest -m integration

Each feed is fetched and parsed; the test fails if a feed is unreachable,
returns non-XML, or yields zero parseable items.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import fetch_podcasts
import fetch_rss

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "config" / "sources.json"


def _load():
    return json.loads(SOURCES.read_text(encoding="utf-8"))


def _flatten():
    """Yield (category, entry) for every RSS feed in sources.json."""
    data = _load()
    for cat in ("podcasts", "blogs", "youtube"):
        for e in data[cat]:
            yield cat, e


_ALL_FEEDS = list(_flatten())


@pytest.mark.integration
@pytest.mark.parametrize(
    "category,entry",
    _ALL_FEEDS,
    ids=[f"{c}-{e['name']}" for c, e in _ALL_FEEDS],
)
def test_feed_is_reachable_and_has_items(category, entry):
    items = fetch_rss.fetch_feed(entry["rss"], timeout=20)
    assert items, f"[{category}] {entry['name']} ({entry['rss']}) returned 0 items"
    assert any(i.get("title") for i in items), (
        f"[{category}] {entry['name']}: no titles"
    )


@pytest.mark.integration
def test_fetch_all_podcasts_pipeline():
    """End-to-end: fetch every podcast feed without leader filtering."""
    data = _load()
    out = fetch_podcasts.fetch_all(
        podcasts=data["podcasts"],
        leaders=data["x_users"],
        max_items=5,
        require_leader_match=False,
    )
    assert out, "no podcast episodes parsed"
    for ep in out:
        assert ep.get("title")
        assert ep.get("source_name")


@pytest.mark.integration
def test_blogs_releases_youtube_pipeline():
    """End-to-end: fetch blogs/youtube via fetch_rss + trending via API."""
    import fetch_github_trending

    data = _load()
    blogs = fetch_rss.fetch_many(data["blogs"], kind="blog", max_items=2,
                                 role_template="By {publisher}")
    videos = fetch_rss.fetch_many(data["youtube"], kind="video", max_items=2,
                                  role_template="Channel · {channel}")
    trending_cfg = data.get("github_trending", {})
    releases = fetch_github_trending.fetch_trending(
        topics=trending_cfg.get("topics"),
        min_stars=trending_cfg.get("min_stars", 1000),
        lookback_days=trending_cfg.get("lookback_days", 14),
        max_repos=5,
    )

    assert blogs, "no blog entries parsed"
    assert releases, "no trending repos returned"
    assert videos, "no video entries parsed"
    for item in blogs + releases + videos:
        assert item["kind"] in {"blog", "release", "video"}
        assert item["source_name"]
