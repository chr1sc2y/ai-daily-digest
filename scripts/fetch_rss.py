"""Generic RSS / Atom feed fetcher.

Used by ``fetch_podcasts`` for podcast feeds and directly by ``run.py`` for
blogs, GitHub Releases and YouTube channel feeds. All of those expose
RFC-822 / Atom XML, so a single parser works for every category.
"""
from __future__ import annotations

import logging
import re
from datetime import timezone
from typing import Iterable

import feedparser
import requests
from dateutil import parser as dateparser

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch_feed(rss_url: str, timeout: int = 12) -> list[dict]:
    """Return a list of normalized entry dicts for a single RSS/Atom feed.

    The shape of each dict is::

        {
            "title":     str,
            "summary":   str,
            "link":      str,
            "author":    str,
            "keywords":  str,    # space-joined <category> terms
            "published": datetime | None,  # always tz-aware (UTC if missing)
        }
    """
    resp = requests.get(rss_url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)

    items: list[dict] = []
    for entry in parsed.entries:
        published = None
        for key in ("published", "updated", "created"):
            raw = entry.get(key)
            if raw:
                try:
                    published = dateparser.parse(raw)
                    break
                except (ValueError, TypeError):
                    continue
        if published and published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)

        summary = entry.get("summary", "") or entry.get("subtitle", "")
        keywords = ""
        tags = entry.get("tags") or []
        if tags:
            keywords = " ".join(t.get("term", "") for t in tags if isinstance(t, dict))

        items.append(
            {
                "title": (entry.get("title") or "").strip(),
                "summary": summary.strip() if summary else "",
                "link": (entry.get("link") or "").strip(),
                "author": (entry.get("author") or "").strip(),
                "keywords": keywords.strip(),
                "published": published,
            }
        )
    return items


def fetch_many(
    feeds: Iterable[dict],
    *,
    kind: str,
    max_items: int = 5,
    role_template: str = "",
) -> list[dict]:
    """Fetch every feed in ``feeds`` (each: ``{name, rss, ...}``) and tag the
    items with our common ``kind`` / ``source_*`` fields used by the renderer.

    ``role_template`` is a Python format string evaluated with the source dict
    (e.g. ``"Hosted by {host}"`` or ``"Releases · {repo}"``). Empty string =
    leave ``source_role`` blank.
    """
    out: list[dict] = []
    for src in feeds:
        url = src.get("rss")
        if not url:
            continue
        try:
            items = fetch_feed(url)
        except Exception as exc:  # pragma: no cover - network failures
            log.warning("[%s] feed failed for %s: %s", kind, src.get("name"), exc)
            continue

        log.debug("[%s] %s -> %d items", kind, src.get("name"), len(items))
        for item in items[:max_items]:
            item["kind"] = kind
            item["source_name"] = src.get("name", "")
            item["source_handle"] = src.get("name", "")
            try:
                item["source_role"] = role_template.format(**src) if role_template else ""
            except KeyError:
                item["source_role"] = ""
            out.append(item)
    return out


def canonical_url(url: str) -> str:
    """Normalize a URL for dedup: lower-case host, drop tracking params,
    strip trailing slash. Does not follow redirects.
    """
    if not url:
        return ""
    url = url.strip()
    # Strip common tracking params.
    url = re.sub(r"([?&])(utm_[^=&]+|fbclid|gclid|ref|si)=[^&]*", r"\1", url)
    url = re.sub(r"[?&]+$", "", url)
    # Normalize scheme + host case.
    m = re.match(r"^(https?)://([^/]+)(/.*)?$", url, flags=re.IGNORECASE)
    if not m:
        return url
    scheme, host, path = m.group(1).lower(), m.group(2).lower(), m.group(3) or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return f"{scheme}://{host}{path}"


def dedup(items: list[dict]) -> list[dict]:
    """Remove items whose canonical link has already been seen.

    Items without a link are kept (we have no good key for them).
    Order is preserved; the first occurrence wins.
    """
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        link = canonical_url(item.get("link", ""))
        if not link:
            out.append(item)
            continue
        if link in seen:
            continue
        seen.add(link)
        out.append(item)
    return out
