"""Fetch latest podcast episodes from public RSS feeds.

We pull every episode from each feed in the configured window, then keep an
episode only if at least one of the AI thought leaders' names or handles
appears in the title / summary / author / itunes:keywords field.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable

import fetch_rss

log = logging.getLogger(__name__)


def _build_keywords(leaders: Iterable[dict]) -> list[tuple[str, list[re.Pattern]]]:
    """For each leader build a list of regex patterns to look for."""
    out: list[tuple[str, list[re.Pattern]]] = []
    for leader in leaders:
        terms: set[str] = set()
        name = (leader.get("name") or "").strip()
        handle = (leader.get("handle") or "").strip()
        if name:
            terms.add(name)
            # also last name on its own (helps "Karpathy", "Hassabis", ...)
            parts = [p for p in re.split(r"\s+", name) if len(p) > 3]
            if parts:
                terms.add(parts[-1])
        if handle:
            terms.add(handle)
            terms.add("@" + handle)
        patterns = [re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE) for t in terms]
        out.append((name or handle, patterns))
    return out


def _matched_leader(text: str, leader_patterns) -> str | None:
    if not text:
        return None
    for leader_name, patterns in leader_patterns:
        for pat in patterns:
            if pat.search(text):
                return leader_name
    return None


# Re-exported for backward compatibility with existing tests.
def _fetch_feed(rss_url: str, timeout: int = 12) -> list[dict]:
    items = fetch_rss.fetch_feed(rss_url, timeout=timeout)
    for it in items:
        it["kind"] = "podcast"
    return items


def fetch_all(
    podcasts: Iterable[dict],
    leaders: Iterable[dict] | None = None,
    max_items: int = 5,
    require_leader_match: bool = True,
) -> list[dict]:
    """Return episodes; if ``require_leader_match`` and ``leaders`` are given,
    only episodes whose text matches a leader name/handle are kept.
    """
    leader_patterns = _build_keywords(leaders or [])
    out: list[dict] = []
    for pod in podcasts:
        try:
            items = _fetch_feed(pod["rss"])
        except Exception as exc:  # pragma: no cover - network failures
            log.warning("Podcast fetch failed for %s: %s", pod.get("name"), exc)
            continue

        kept: list[dict] = []
        for item in items:
            haystack = " ".join(
                [
                    item.get("title", ""),
                    item.get("summary", ""),
                    item.get("author", ""),
                    item.get("keywords", ""),
                ]
            )
            matched = _matched_leader(haystack, leader_patterns) if leader_patterns else None
            if require_leader_match and leader_patterns and not matched:
                continue
            item["source_name"] = pod.get("name", "")
            host = pod.get("host", "")
            if matched:
                item["source_role"] = f"Featuring {matched}"
            else:
                item["source_role"] = f"Hosted by {host}" if host else ""
            item["source_handle"] = pod.get("name", "")
            kept.append(item)
            if len(kept) >= max_items:
                break

        out.extend(kept)
    return out
