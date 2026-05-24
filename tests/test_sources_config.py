"""Validate config/sources.json structurally (no network)."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "config" / "sources.json"

RSS_CATEGORIES = ("podcasts", "blogs", "youtube")


def _load():
    return json.loads(SOURCES.read_text(encoding="utf-8"))


def test_sources_file_is_valid_json():
    data = _load()
    for key in ("x_users", *RSS_CATEGORIES):
        assert key in data, f"{key} missing from sources.json"


def test_x_users_have_required_fields():
    data = _load()
    assert len(data["x_users"]) >= 1
    for u in data["x_users"]:
        assert isinstance(u.get("name"), str) and u["name"]
        assert isinstance(u.get("handle"), str) and u["handle"]
        assert "@" not in u["handle"]
        assert " " not in u["handle"]


@pytest.mark.parametrize("category", RSS_CATEGORIES)
def test_rss_category_entries_have_required_fields(category):
    data = _load()
    entries = data[category]
    assert len(entries) >= 1, f"{category} is empty"
    for e in entries:
        assert isinstance(e.get("name"), str) and e["name"]
        assert isinstance(e.get("rss"), str) and e["rss"]
        parsed = urlparse(e["rss"])
        assert parsed.scheme in ("http", "https"), e
        assert parsed.netloc, f"{category}/{e['name']} missing netloc"


def test_no_duplicate_handles_or_rss():
    data = _load()
    handles = [u["handle"].lower() for u in data["x_users"]]
    assert len(handles) == len(set(handles)), "duplicate X handle"

    all_rss: list[str] = []
    for cat in RSS_CATEGORIES:
        all_rss.extend(e["rss"] for e in data[cat])
    assert len(all_rss) == len(set(all_rss)), "duplicate RSS URL across feeds"


def test_x_curation_includes_developer_signal_and_prunes_known_noise():
    data = _load()
    handles = {u["handle"].lower() for u in data["x_users"]}
    assert "thsottiaux" in handles
    assert "garrytan" not in handles
    assert "mattturck" not in handles


def test_youtube_feeds_use_channel_id_format():
    data = _load()
    for entry in data["youtube"]:
        assert "channel_id=" in entry["rss"], entry


def test_secrets_example_exists_and_has_required_keys():
    example = ROOT / "config" / "secrets.example.json"
    data = json.loads(example.read_text(encoding="utf-8"))
    assert "apify_token" in data
