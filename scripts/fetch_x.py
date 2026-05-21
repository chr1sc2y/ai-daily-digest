"""Fetch latest X/Twitter posts via Apify (kaitoeasyapi tweet scraper).

Configuration is loaded from ``config/secrets.json`` (gitignored). Copy
``config/secrets.example.json`` to ``config/secrets.json`` and fill in your
real Apify token. We do NOT read system environment variables here on
purpose — secrets live in the file only.

Schema of ``config/secrets.json``::

    {
      "apify_token":           "apify_api_xxx...",
      "apify_actor":           "kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest",
      "apify_lookback_hours":  24
    }

In CI (GitHub Actions) the workflow generates ``config/secrets.json`` on the
fly from the ``APIFY_TOKEN`` repository secret — see ``.github/workflows/daily.yml``.
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

DEFAULT_APIFY_ACTOR = (
    "kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest"
)
DEFAULT_LOOKBACK_HOURS = 24


def _parse_date(raw) -> datetime | None:
    if not raw:
        return None
    try:
        dt = dateparser.parse(raw)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _load_secrets() -> dict[str, Any]:
    if not SECRETS_PATH.exists():
        raise RuntimeError(
            f"Missing {SECRETS_PATH}. Copy config/secrets.example.json to "
            f"config/secrets.json and fill in your Apify token."
        )
    return json.loads(SECRETS_PATH.read_text(encoding="utf-8"))


def _fetch_apify(
    handle: str,
    max_items: int,
    token: str,
    actor: str,
    lookback_hours: int,
) -> list[dict]:
    """Run the kaitoeasyapi tweet scraper actor synchronously."""
    url = (
        f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
    )
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    payload = {
        "twitterHandles": [handle],
        "maxItems": max_items,
        "sort": "Latest",
        # kaitoeasyapi accepts ISO-8601 date strings; we pass UTC.
        "start": since.strftime("%Y-%m-%d"),
    }
    log.info(
        "X[apify]: scraping @%s (max %d, since %s)",
        handle, max_items, payload["start"],
    )
    resp = requests.post(url, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    out: list[dict] = []
    for t in data:
        text = t.get("text") or t.get("full_text") or ""
        link = t.get("url") or t.get("twitterUrl") or ""
        published = _parse_date(t.get("createdAt") or t.get("created_at"))
        # Drop anything older than the cutoff just in case the actor returns
        # extra results.
        if published and published < since:
            continue
        out.append(
            {
                "kind": "x",
                "title": text[:120],
                "summary": text,
                "link": link,
                "author": handle,
                "published": published,
            }
        )
    return out[:max_items]


def fetch_user(handle: str, max_items: int = 5) -> list[dict]:
    secrets = _load_secrets()
    token = secrets.get("apify_token")
    if not token or token.startswith("apify_api_xxx"):
        raise RuntimeError(
            "config/secrets.json: 'apify_token' is missing or still set to the "
            "placeholder value."
        )
    actor = secrets.get("apify_actor") or DEFAULT_APIFY_ACTOR
    lookback = int(secrets.get("apify_lookback_hours") or DEFAULT_LOOKBACK_HOURS)
    try:
        return _fetch_apify(handle, max_items, token, actor, lookback)
    except Exception as exc:
        log.warning("X[apify]: failed for @%s: %s", handle, exc)
        return []


def fetch_all(users: list[dict], instances=None, max_items: int = 5) -> list[dict]:
    # ``instances`` kept for backward compatibility; not used.
    log.info("X provider: apify")
    out: list[dict] = []
    for user in users:
        handle = user["handle"]
        items = fetch_user(handle, max_items=max_items)
        for item in items:
            item["source_name"] = user.get("name", handle)
            item["source_role"] = user.get("role", "")
            item["source_handle"] = handle
            out.append(item)
    return out
