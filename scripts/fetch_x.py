"""Fetch latest X/Twitter posts via Apify (kaitoeasyapi tweet scraper).

Configuration is loaded from ``config/secrets.json`` (gitignored). Copy
``config/secrets.example.json`` to ``config/secrets.json`` and fill in your
real Apify token. We do NOT read system environment variables here on
purpose — secrets live in the file only.

Schema of ``config/secrets.json``::

    {
      "apify_token":             "apify_api_xxx...",
      "apify_actor":             "kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest",
      "apify_monthly_budget_usd": 4.0
    }

``apify_monthly_budget_usd`` is a soft cap on this month's Apify spend.
Before each batch run we query ``GET /v2/users/me/usage/monthly``; if
the current cycle has already used more than this many USD we skip the
X fetch entirely and return an empty list. Default is 4.0 USD which
keeps us inside the platform's free $5 monthly credit.

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
DEFAULT_MONTHLY_BUDGET_USD = 4.0
MOCK_TEXT_MARKERS = (
    "From KaitoEasyAPI, a reminder:",
    "Thus, we returned N pieces of mock data",
)
HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
STATUS_URL_RE = re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/([^/?#]+)/status/", re.I)
LEADING_MENTION_RE = re.compile(r"^\s*@[A-Za-z0-9_]{1,15}\b")
RETWEET_PREFIX_RE = re.compile(r"^\s*RT\s+@[A-Za-z0-9_]{1,15}:")
REPLY_FLAG_KEYS = ("isReply", "is_reply")
REPLY_ID_KEYS = (
    "inReplyToId",
    "inReplyToStatusId",
    "in_reply_to_status_id",
    "inReplyToUserId",
    "in_reply_to_user_id",
    "replyToId",
)
RETWEET_FLAG_KEYS = ("isRetweet", "retweeted", "is_retweet")


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


def _is_reply(tweet: dict, text: str) -> bool:
    if any(tweet.get(key) is True for key in REPLY_FLAG_KEYS):
        return True
    if any(tweet.get(key) for key in REPLY_ID_KEYS):
        return True
    return bool(LEADING_MENTION_RE.match(text))


def _is_retweet(tweet: dict, text: str) -> bool:
    if any(tweet.get(key) for key in RETWEET_FLAG_KEYS):
        return True
    return bool(RETWEET_PREFIX_RE.match(text))


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
    if _is_reply(tweet, text) or _is_retweet(tweet, text):
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


def _monthly_usage_usd(token: str, *, timeout: int = 15) -> float | None:
    """Return this Apify cycle's spend in USD, or None on any failure.

    We never let a billing-API hiccup take down the digest run. Callers
    treat ``None`` as "skip the budget check" (we'd rather fetch than
    silently produce empty segments).
    """
    try:
        resp = requests.get(
            "https://api.apify.com/v2/users/me/usage/monthly",
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        # Pre-discount is the most conservative reading; we want to stop
        # before billing kicks in, not after.
        return float(data.get("totalUsageCreditsUsdBeforeVolumeDiscount") or 0.0)
    except (requests.RequestException, ValueError, TypeError) as exc:
        log.warning("X[apify]: monthly-usage check failed: %s", exc)
        return None


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
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict]:
    """Backward-compatible single-handle wrapper around the batch scraper.

    Kept because the unit-test suite imports it directly. New callers should
    use ``_fetch_apify_batch``.
    """
    return _fetch_apify_batch([handle], max_items, token, actor, lookback_hours, since, until)


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

    # Soft monthly-budget guard. If usage already exceeds the cap, skip
    # the X fetch entirely so we never silently overshoot the free credit.
    budget = float(secrets.get("apify_monthly_budget_usd") or DEFAULT_MONTHLY_BUDGET_USD)
    used = _monthly_usage_usd(token)
    if used is not None and used >= budget:
        log.error(
            "X[apify]: monthly usage $%.2f >= budget $%.2f, skipping X fetch.",
            used, budget,
        )
        return []
    if used is not None:
        log.info("X[apify]: monthly usage $%.4f / budget $%.2f", used, budget)

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
