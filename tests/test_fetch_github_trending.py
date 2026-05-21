"""Unit tests for fetch_github_trending (mocked HTTP)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import requests

import fetch_github_trending as ght


def _fake_repo(full_name: str, stars: int, desc: str = "An AI repo",
               pushed: str = "2026-05-19T10:00:00Z") -> dict:
    owner = full_name.split("/")[0]
    return {
        "full_name": full_name,
        "owner": {"login": owner},
        "description": desc,
        "stargazers_count": stars,
        "pushed_at": pushed,
        "html_url": f"https://github.com/{full_name}",
    }


def _mock_response(items: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"items": items}
    return resp


def test_to_item_shape():
    item = ght._to_item(_fake_repo("foo/bar", 1234, "A reasoning lib"))
    assert item["kind"] == "release"
    assert item["source_name"] == "foo/bar"
    assert item["source_role"] == "foo/bar"
    assert item["author"] == "foo"
    assert "1,234" in item["summary"]
    assert "A reasoning lib" in item["summary"]
    assert isinstance(item["published"], datetime)
    assert item["published"].tzinfo is not None


def test_to_item_handles_missing_description():
    item = ght._to_item(_fake_repo("foo/bar", 50, ""))
    assert item["title"] == "foo/bar"
    assert "⭐" in item["summary"]


def test_fetch_trending_dedups_across_topics():
    repo_a = _fake_repo("acme/llm", 5000)
    repo_b = _fake_repo("acme/agent", 3000)
    repo_a_higher = _fake_repo("acme/llm", 6000)  # second topic shows newer star count

    with patch.object(ght.requests, "get") as mock_get:
        mock_get.side_effect = [
            _mock_response([repo_a, repo_b]),
            _mock_response([repo_a_higher]),
        ]
        out = ght.fetch_trending(topics=["llm", "ai-agents"], min_stars=100, max_repos=10)

    full_names = [i["source_name"] for i in out]
    assert full_names == ["acme/llm", "acme/agent"]
    # dedup kept the higher-star copy
    assert "6,000" in out[0]["summary"]


def test_fetch_trending_respects_max_repos():
    repos = [_fake_repo(f"o/r{i}", 1000 + i) for i in range(50)]
    with patch.object(ght.requests, "get", return_value=_mock_response(repos)):
        out = ght.fetch_trending(topics=["llm"], max_repos=5)
    assert len(out) == 5
    # sorted by stars desc
    assert out[0]["source_name"] == "o/r49"


def test_fetch_trending_continues_on_topic_failure():
    with patch.object(ght.requests, "get") as mock_get:
        mock_get.side_effect = [
            requests.RequestException("boom"),
            _mock_response([_fake_repo("ok/repo", 999)]),
        ]
        out = ght.fetch_trending(topics=["llm", "ai-agents"], min_stars=100)
    assert len(out) == 1
    assert out[0]["source_name"] == "ok/repo"


def test_fetch_trending_empty_when_all_topics_fail():
    with patch.object(ght.requests, "get", side_effect=requests.RequestException("x")):
        out = ght.fetch_trending(topics=["llm", "rag"])
    assert out == []


def test_load_token_returns_none_when_no_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(ght, "SECRETS_PATH", tmp_path / "missing.json")
    assert ght._load_token() is None


def test_load_token_reads_github_token(tmp_path, monkeypatch):
    p = tmp_path / "secrets.json"
    p.write_text('{"github_token": "ghp_xxx"}', encoding="utf-8")
    monkeypatch.setattr(ght, "SECRETS_PATH", p)
    assert ght._load_token() == "ghp_xxx"


def test_load_token_returns_none_for_empty_string(tmp_path, monkeypatch):
    p = tmp_path / "secrets.json"
    p.write_text('{"github_token": ""}', encoding="utf-8")
    monkeypatch.setattr(ght, "SECRETS_PATH", p)
    assert ght._load_token() is None


def test_parse_date_handles_iso():
    dt = ght._parse_date("2026-05-19T10:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt == datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_date_handles_invalid_input():
    assert ght._parse_date("") is None
    assert ght._parse_date(None) is None
    assert ght._parse_date("not a date") is None
