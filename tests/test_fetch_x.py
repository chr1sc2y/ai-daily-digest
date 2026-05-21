"""Unit tests for the Apify-backed X fetcher.

These tests stub out ``requests.post`` so nothing hits the network.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

import fetch_x


# ---------------------------------------------------------------------------
# _load_secrets
# ---------------------------------------------------------------------------

def _write_secrets(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_load_secrets_returns_parsed_json(monkeypatch, tmp_path):
    secrets_file = _write_secrets(tmp_path, {"apify_token": "abc"})
    monkeypatch.setattr(fetch_x, "SECRETS_PATH", secrets_file)
    assert fetch_x._load_secrets() == {"apify_token": "abc"}


def test_load_secrets_missing_file_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_x, "SECRETS_PATH", tmp_path / "missing.json")
    with pytest.raises(RuntimeError, match="Missing"):
        fetch_x._load_secrets()


def test_load_secrets_invalid_json_raises(monkeypatch, tmp_path):
    bad = tmp_path / "secrets.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(fetch_x, "SECRETS_PATH", bad)
    with pytest.raises(json.JSONDecodeError):
        fetch_x._load_secrets()


# ---------------------------------------------------------------------------
# _fetch_apify
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_fetch_apify_normalizes_response():
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = [
        {"text": "hello world", "url": "https://x.com/sama/status/1", "createdAt": now_iso},
        {"full_text": "another", "twitterUrl": "https://x.com/sama/status/2", "created_at": now_iso},
    ]
    with patch.object(fetch_x.requests, "post", return_value=_FakeResp(payload)):
        out = fetch_x._fetch_apify(
            handle="sama",
            max_items=10,
            token="t",
            actor="a",
            lookback_hours=24,
        )

    assert len(out) == 2
    assert out[0]["kind"] == "x"
    assert out[0]["title"] == "hello world"
    assert out[0]["summary"] == "hello world"
    assert out[0]["link"] == "https://x.com/sama/status/1"
    assert out[0]["author"] == "sama"
    assert out[0]["published"] is not None
    # second item picks up full_text + twitterUrl + created_at
    assert out[1]["title"] == "another"
    assert out[1]["link"] == "https://x.com/sama/status/2"


def test_fetch_apify_drops_items_older_than_cutoff():
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    fresh = datetime.now(timezone.utc).isoformat()
    payload = [
        {"text": "stale tweet", "createdAt": old},
        {"text": "fresh tweet", "createdAt": fresh},
    ]
    with patch.object(fetch_x.requests, "post", return_value=_FakeResp(payload)):
        out = fetch_x._fetch_apify(
            handle="sama", max_items=10, token="t", actor="a", lookback_hours=24,
        )

    assert len(out) == 1
    assert out[0]["title"] == "fresh tweet"


def test_fetch_apify_respects_max_items():
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = [{"text": f"#{i}", "createdAt": now_iso} for i in range(50)]
    with patch.object(fetch_x.requests, "post", return_value=_FakeResp(payload)):
        out = fetch_x._fetch_apify(
            handle="sama", max_items=3, token="t", actor="a", lookback_hours=24,
        )
    assert len(out) == 3


def test_fetch_apify_passes_lookback_in_payload():
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        captured["headers"] = headers
        return _FakeResp([])

    with patch.object(fetch_x.requests, "post", side_effect=fake_post):
        fetch_x._fetch_apify(
            handle="elonmusk",
            max_items=5,
            token="my-token",
            actor="my-actor",
            lookback_hours=72,
        )

    assert "my-actor" in captured["url"]
    assert "my-token" not in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer my-token"
    assert captured["payload"]["twitterHandles"] == ["elonmusk"]
    assert captured["payload"]["maxItems"] == 5
    assert captured["payload"]["sort"] == "Latest"
    # start should be a YYYY-MM-DD string for ~3 days ago
    expected = (datetime.now(timezone.utc) - timedelta(hours=72)).strftime("%Y-%m-%d")
    assert captured["payload"]["start"] == expected


# ---------------------------------------------------------------------------
# fetch_user / fetch_all
# ---------------------------------------------------------------------------

def test_fetch_user_requires_token(monkeypatch, tmp_path):
    secrets_file = _write_secrets(tmp_path, {"apify_token": "apify_api_xxx_placeholder"})
    monkeypatch.setattr(fetch_x, "SECRETS_PATH", secrets_file)
    with pytest.raises(RuntimeError, match="apify_token"):
        fetch_x.fetch_user("sama")


def test_fetch_user_swallows_apify_failure(monkeypatch, tmp_path):
    secrets_file = _write_secrets(tmp_path, {"apify_token": "real_token"})
    monkeypatch.setattr(fetch_x, "SECRETS_PATH", secrets_file)

    def boom(*a, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(fetch_x, "_fetch_apify", boom)
    assert fetch_x.fetch_user("sama") == []


def test_fetch_all_attaches_source_metadata(monkeypatch, tmp_path):
    secrets_file = _write_secrets(tmp_path, {"apify_token": "real_token"})
    monkeypatch.setattr(fetch_x, "SECRETS_PATH", secrets_file)

    def fake_apify(handle, max_items, token, actor, lookback_hours):
        return [{"kind": "x", "title": "t", "summary": "t", "link": "", "author": handle, "published": None}]

    monkeypatch.setattr(fetch_x, "_fetch_apify", fake_apify)

    users = [{"name": "Sam Altman", "handle": "sama", "role": "CEO, OpenAI"}]
    out = fetch_x.fetch_all(users, max_items=3)
    assert len(out) == 1
    assert out[0]["source_name"] == "Sam Altman"
    assert out[0]["source_role"] == "CEO, OpenAI"
    assert out[0]["source_handle"] == "sama"
