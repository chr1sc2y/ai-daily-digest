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
import re
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
MOCK_TEXT_MARKERS = (
    "From KaitoEasyAPI, a reminder:",
    "Thus, we returned N pieces of mock data",
)
HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
STATUS_URL_RE = re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/([^/?#]+)/status/", re.I)


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


def _is_provider_mock_text(text: str) -> bool:
    return any(marker in text for marker in MOCK_TEXT_MARKERS)


def _normalize_handle(raw: Any) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    url_match = STATUS_URL_RE.search(text)
    if url_match:
        text = url_match.group(1)
    text = text.strip().lstrip("@").strip("/")
    return text.lower() if HANDLE_RE.fullmatch(text) else ""


def _extract_handle(tweet: dict) -> str:
    for key in ("username", "userName", "screen_name", "handle", "twitterHandle"):
        handle = _normalize_handle(tweet.get(key))
        if handle:
            return handle

    for key in ("author", "user"):
        value = tweet.get(key)
        if isinstance(value, dict):
            for nested in ("username", "userName", "screen_name", "handle", "twitterHandle"):
                handle = _normalize_handle(value.get(nested))
                if handle:
                    return handle
        elif isinstance(value, str):
            handle = _normalize_handle(value)
            if handle:
                return handle

    for key in ("url", "twitterUrl", "link"):
        handle = _normalize_handle(tweet.get(key))
        if handle:
            return handle
    return ""


def _tweet_id(tweet: dict) -> str:
    for key in ("id", "tweetID", "tweetId", "conversationId"):
        raw = tweet.get(key)
        if raw:
            return str(raw)
    return ""


def _tweet_to_item(tweet: dict, *, handle: str, since: datetime) -> dict | None:
    text = tweet.get("text") or tweet.get("full_text") or tweet.get("fullText") or tweet.get("tweetText") or ""
    if not text or _is_provider_mock_text(text):
        return None

    published = _parse_date(tweet.get("createdAt") or tweet.get("created_at") or tweet.get("createdAtISO"))
    if published is None or published < since:
        return None

    link = tweet.get("url") or tweet.get("twitterUrl") or tweet.get("link") or ""
    if not link:
        tweet_id = _tweet_id(tweet)
        if tweet_id:
            link = f"https://x.com/{handle}/status/{tweet_id}"

    return {
        "kind": "x",
        "title": text[:120],
        "summary": text,
        "link": link,
        "author": handle,
        "published": published,
    }


def _search_term(handle: str, since: datetime, until: datetime) -> str:
    return f"from:{handle} since_time:{int(since.timestamp())} until_time:{int(until.timestamp())}"


def _fetch_apify_batch(
    handles: list[str],
    max_items: int,
    token: str,
    actor: str,
    lookback_hours: int,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict]:
    """Run the kaitoeasyapi tweet scraper actor once for many handles."""
    handle_map = {
        normalized: handle.lstrip("@")
        for handle in handles
        if (normalized := _normalize_handle(handle))
    }
    if not handle_map:
        return []

    until = (until or datetime.now(timezone.utc)).astimezone(timezone.utc)
    since = (since or (until - timedelta(hours=lookback_hours))).astimezone(timezone.utc)
    url = f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
    payload = {
        "searchTerms": [_search_term(handle, since, until) for handle in handle_map.values()],
        # Kaito's current schema treats maxItems as per search term and documents
        # 20 as the minimum. We still clip to max_items locally after parsing.
        "maxItems": max(20, max_items),
        "queryType": "Latest",
    }
    log.info(
        "X[apify]: scraping %d handles in one batch (max %d each, %s to %s)",
        len(handle_map), max_items, since.isoformat(), until.isoformat(),
    )
    resp = requests.post(url, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=180)
    resp.raise_for_status()
    data = resp.json()

    grouped: dict[str, list[dict]] = {handle: [] for handle in handle_map.values()}
    for tweet in data:
        normalized = _extract_handle(tweet)
        handle = handle_map.get(normalized)
        if not handle or len(grouped[handle]) >= max_items:
            continue
        item = _tweet_to_item(tweet, handle=handle, since=since)
        if item:
            grouped[handle].append(item)

    out: list[dict] = []
    for handle in handle_map.values():
        out.extend(grouped[handle])
    return out


def _fetch_apify(
    handle: str,
    max_items: int,
    token: str,
    actor: str,
    lookback_hours: int,
) -> list[dict]:
    """Backward-compatible single-handle wrapper around the batch scraper."""
    return _fetch_apify_batch([handle], max_items, token, actor, lookback_hours)


def fetch_user(
    handle: str,
    max_items: int = 5,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict]:
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
        return _fetch_apify_batch([handle], max_items, token, actor, lookback, since, until)
    except Exception as exc:
        log.warning("X[apify]: failed for @%s: %s", handle, exc)
        return []


def fetch_all(
    users: list[dict],
    instances=None,
    max_items: int = 5,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict]:
    # ``instances`` kept for backward compatibility; not used.
    log.info("X provider: apify")
    secrets = _load_secrets()
    token = secrets.get("apify_token")
    if not token or token.startswith("apify_api_xxx"):
        raise RuntimeError(
            "config/secrets.json: 'apify_token' is missing or still set to the "
            "placeholder value."
        )
    actor = secrets.get("apify_actor") or DEFAULT_APIFY_ACTOR
    lookback = int(secrets.get("apify_lookback_hours") or DEFAULT_LOOKBACK_HOURS)

    out: list[dict] = []
    users_by_handle = {_normalize_handle(user["handle"]): user for user in users}
    try:
        items = _fetch_apify_batch(
            [user["handle"] for user in users],
            max_items,
            token,
            actor,
            lookback,
            since,
            until,
        )
    except Exception as exc:
        log.warning("X[apify]: batch failed: %s", exc)
        return []

    for item in items:
        user = users_by_handle.get(_normalize_handle(item.get("author")))
        if not user:
            continue
        handle = user["handle"]
        item["source_name"] = user.get("name", handle)
        item["source_role"] = user.get("role", "")
        item["source_handle"] = handle
        out.append(item)
    return out
