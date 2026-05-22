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
        {"text": "stale tweet", "url": "https://x.com/sama/status/old", "createdAt": old},
        {"text": "fresh tweet", "url": "https://x.com/sama/status/fresh", "createdAt": fresh},
    ]
    with patch.object(fetch_x.requests, "post", return_value=_FakeResp(payload)):
        out = fetch_x._fetch_apify(
            handle="sama", max_items=10, token="t", actor="a", lookback_hours=24,
        )

    assert len(out) == 1
    assert out[0]["title"] == "fresh tweet"


def test_fetch_apify_drops_provider_mock_text():
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = [
        {
            "text": "From KaitoEasyAPI, a reminder:Thus, we returned N pieces of mock data.",
            "url": "https://x.com/sama/status/mock",
            "createdAt": now_iso,
        },
        {"text": "real tweet", "url": "https://x.com/sama/status/real", "createdAt": now_iso},
    ]
    with patch.object(fetch_x.requests, "post", return_value=_FakeResp(payload)):
        out = fetch_x._fetch_apify(
            handle="sama", max_items=10, token="t", actor="a", lookback_hours=24,
        )

    assert len(out) == 1
    assert out[0]["title"] == "real tweet"


def test_fetch_apify_drops_replies_by_flag_and_leading_mention():
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = [
        {"text": "@someone thanks!", "url": "https://x.com/sama/status/r1", "createdAt": now_iso},
        {"text": "original thought", "url": "https://x.com/sama/status/r2", "createdAt": now_iso, "isReply": True},
        {"text": "real post about agents", "url": "https://x.com/sama/status/r3", "createdAt": now_iso},
        {"text": "another", "url": "https://x.com/sama/status/r4", "createdAt": now_iso, "inReplyToId": "9999"},
    ]
    with patch.object(fetch_x.requests, "post", return_value=_FakeResp(payload)):
        out = fetch_x._fetch_apify(
            handle="sama", max_items=10, token="t", actor="a", lookback_hours=24,
        )
    assert [item["title"] for item in out] == ["real post about agents"]


def test_fetch_apify_drops_retweets():
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = [
        {"text": "RT @someone: cool paper", "url": "https://x.com/sama/status/rt1", "createdAt": now_iso},
        {"text": "fresh original tweet", "url": "https://x.com/sama/status/rt2", "createdAt": now_iso},
        {"text": "via flag", "url": "https://x.com/sama/status/rt3", "createdAt": now_iso, "isRetweet": True},
    ]
    with patch.object(fetch_x.requests, "post", return_value=_FakeResp(payload)):
        out = fetch_x._fetch_apify(
            handle="sama", max_items=10, token="t", actor="a", lookback_hours=24,
        )
    assert [item["title"] for item in out] == ["fresh original tweet"]


def test_fetch_apify_respects_max_items():
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = [
        {"text": f"#{i}", "url": f"https://x.com/sama/status/{i}", "createdAt": now_iso}
        for i in range(50)
    ]
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
    assert captured["payload"]["maxItems"] == 20
    assert captured["payload"]["queryType"] == "Latest"
    assert len(captured["payload"]["searchTerms"]) == 1
    term = captured["payload"]["searchTerms"][0]
    assert term.startswith("from:elonmusk since_time:")
    expected = int((datetime.now(timezone.utc) - timedelta(hours=72)).timestamp())
    actual = int(term.split("since_time:", 1)[1].split(" ", 1)[0])
    assert abs(actual - expected) < 5


def test_fetch_apify_batch_uses_search_terms_and_groups_by_handle():
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = [
        {"text": "sam", "url": "https://x.com/sama/status/1", "createdAt": now_iso},
        {"text": "andrej", "url": "https://x.com/karpathy/status/2", "createdAt": now_iso},
    ]
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["payload"] = json
        return _FakeResp(payload)

    with patch.object(fetch_x.requests, "post", side_effect=fake_post):
        out = fetch_x._fetch_apify_batch(
            ["sama", "karpathy"],
            max_items=2,
            token="t",
            actor="a",
            lookback_hours=24,
        )

    assert [item["author"] for item in out] == ["sama", "karpathy"]
    assert len(captured["payload"]["searchTerms"]) == 2
    assert captured["payload"]["searchTerms"][0].startswith("from:sama ")
    assert captured["payload"]["searchTerms"][1].startswith("from:karpathy ")


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

    monkeypatch.setattr(fetch_x, "_fetch_apify_batch", boom)
    assert fetch_x.fetch_user("sama") == []


def test_fetch_all_attaches_source_metadata(monkeypatch, tmp_path):
    secrets_file = _write_secrets(tmp_path, {"apify_token": "real_token"})
    monkeypatch.setattr(fetch_x, "SECRETS_PATH", secrets_file)

    def fake_apify(handles, max_items, token, actor, lookback_hours, since=None, until=None):
        return [{"kind": "x", "title": "t", "summary": "t", "link": "https://x.com/sama/status/1", "author": handles[0], "published": datetime.now(timezone.utc)}]

    monkeypatch.setattr(fetch_x, "_fetch_apify_batch", fake_apify)
    monkeypatch.setattr(fetch_x, "_monthly_usage_usd", lambda token: 0.0)

    users = [{"name": "Sam Altman", "handle": "sama", "role": "CEO, OpenAI"}]
    out = fetch_x.fetch_all(users, max_items=3)
    assert len(out) == 1
    assert out[0]["source_name"] == "Sam Altman"
    assert out[0]["source_role"] == "CEO, OpenAI"
    assert out[0]["source_handle"] == "sama"


def test_fetch_all_skips_when_monthly_budget_exceeded(monkeypatch, tmp_path):
    secrets_file = _write_secrets(
        tmp_path,
        {"apify_token": "real_token", "apify_monthly_budget_usd": 4.0},
    )
    monkeypatch.setattr(fetch_x, "SECRETS_PATH", secrets_file)

    called = {"n": 0}

    def fake_apify(*a, **kw):
        called["n"] += 1
        return []

    monkeypatch.setattr(fetch_x, "_fetch_apify_batch", fake_apify)
    # Pretend we've already spent $4.50 this cycle.
    monkeypatch.setattr(fetch_x, "_monthly_usage_usd", lambda token: 4.5)

    users = [{"name": "Sam Altman", "handle": "sama", "role": "CEO, OpenAI"}]
    out = fetch_x.fetch_all(users)
    assert out == []
    assert called["n"] == 0  # batch fetch must not run


def test_fetch_all_continues_when_usage_check_fails(monkeypatch, tmp_path):
    secrets_file = _write_secrets(tmp_path, {"apify_token": "real_token"})
    monkeypatch.setattr(fetch_x, "SECRETS_PATH", secrets_file)

    called = {"n": 0}

    def fake_apify(handles, max_items, token, actor, lookback_hours, since=None, until=None):
        called["n"] += 1
        return []

    monkeypatch.setattr(fetch_x, "_fetch_apify_batch", fake_apify)
    # Billing API hiccup: usage check returns None. We should not block
    # the fetch on a transient meta-API failure.
    monkeypatch.setattr(fetch_x, "_monthly_usage_usd", lambda token: None)

    fetch_x.fetch_all([{"name": "Sam", "handle": "sama"}])
    assert called["n"] == 1
