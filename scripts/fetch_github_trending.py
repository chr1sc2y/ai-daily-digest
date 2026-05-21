"""Fetch trending AI repositories via the GitHub Search API.

GitHub does not expose an official "trending" RSS, so we proxy it with the
public Search API and filter by topic + stars + recent push activity. No
auth is required for low-volume usage; if a ``github_token`` key is present
in ``config/secrets.json`` we'll send it to raise the rate limit ceiling.

Output items follow the same schema as ``fetch_rss``:

    {
      "kind":         "release",
      "source_name":  "owner/repo",
      "source_role":  "owner/repo",
      "title":        "<repo description>",
      "summary":      "<repo description>",
      "link":         "https://github.com/owner/repo",
      "published":    <datetime, repo pushed_at>,
      "author":       "owner",
    }
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dateutil import parser as dateparser

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
SECRETS_PATH = ROOT / "config" / "secrets.json"

SEARCH_URL = "https://api.github.com/search/repositories"


def _load_token() -> str | None:
    if not SECRETS_PATH.exists():
        return None
    try:
        data = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    token = data.get("github_token")
    return token if token else None


def _parse_date(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        dt = dateparser.parse(raw)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _to_item(repo: dict) -> dict:
    full_name = repo.get("full_name", "")
    owner = repo.get("owner", {}).get("login", "")
    desc = (repo.get("description") or "").strip()
    stars = repo.get("stargazers_count", 0)
    pushed = _parse_date(repo.get("pushed_at"))
    summary = f"⭐ {stars:,} · {desc}" if desc else f"⭐ {stars:,}"
    return {
        "kind":        "release",
        "source_name": full_name,
        "source_role": full_name,
        "title":       desc or full_name,
        "summary":     summary,
        "link":        repo.get("html_url", f"https://github.com/{full_name}"),
        "published":   pushed,
        "author":      owner,
    }


def fetch_trending(
    topics: list[str] | None = None,
    min_stars: int = 1000,
    lookback_days: int = 14,
    max_repos: int = 20,
    timeout: int = 20,
) -> list[dict]:
    """Return AI-tagged repos pushed within ``lookback_days`` and >= ``min_stars``.

    Uses one Search API call per topic and merges the results (dedup by repo
    full_name, keep the highest star count). The default ``max_repos`` caps
    the merged list, sorted by stars descending.
    """
    topics = topics or ["llm", "ai-agents", "generative-ai"]
    pushed_after = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    headers = {"Accept": "application/vnd.github+json"}
    token = _load_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    seen: dict[str, dict] = {}
    for topic in topics:
        q = f"topic:{topic} stars:>={min_stars} pushed:>={pushed_after}"
        params = {"q": q, "sort": "stars", "order": "desc", "per_page": 25}
        try:
            r = requests.get(SEARCH_URL, params=params, headers=headers, timeout=timeout)
            r.raise_for_status()
        except requests.RequestException as exc:
            log.warning("github trending: topic=%s failed: %s", topic, exc)
            continue
        for repo in r.json().get("items", []):
            full = repo.get("full_name")
            if not full:
                continue
            prev = seen.get(full)
            if not prev or repo.get("stargazers_count", 0) > prev.get("stargazers_count", 0):
                seen[full] = repo

    merged = sorted(seen.values(), key=lambda r: r.get("stargazers_count", 0), reverse=True)
    return [_to_item(r) for r in merged[:max_repos]]
