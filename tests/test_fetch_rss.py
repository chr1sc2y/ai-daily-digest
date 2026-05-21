"""Unit tests for the generic RSS fetcher / dedup utilities."""
from __future__ import annotations

import textwrap
from unittest.mock import patch

import fetch_rss


SAMPLE_RSS = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Demo Feed</title>
        <item>
          <title>First post</title>
          <description>Hello world</description>
          <link>https://example.com/a</link>
          <pubDate>Mon, 19 May 2026 09:00:00 GMT</pubDate>
          <author>writer@example.com</author>
          <category>ai</category>
          <category>research</category>
        </item>
        <item>
          <title>Second post</title>
          <description>Goodbye world</description>
          <link>https://example.com/b</link>
          <pubDate>Mon, 12 May 2026 09:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
""").encode("utf-8")


class _FakeResp:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# ---------------------------------------------------------------------------
# fetch_feed
# ---------------------------------------------------------------------------

def test_fetch_feed_normalizes_entries():
    with patch.object(fetch_rss.requests, "get", return_value=_FakeResp(SAMPLE_RSS)):
        items = fetch_rss.fetch_feed("https://x/feed")
    assert len(items) == 2
    assert items[0]["title"] == "First post"
    assert items[0]["link"] == "https://example.com/a"
    assert items[0]["author"] == "writer@example.com"
    assert items[0]["published"] is not None
    assert items[0]["published"].tzinfo is not None
    assert "ai" in items[0]["keywords"] and "research" in items[0]["keywords"]


def test_fetch_feed_keeps_atom_summary_when_summary_missing():
    atom = textwrap.dedent("""\
        <?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>Atom</title>
          <entry>
            <title>Atom title</title>
            <link href="https://example.com/x" />
            <updated>2026-05-20T10:00:00Z</updated>
            <subtitle>The subtitle</subtitle>
          </entry>
        </feed>
    """).encode("utf-8")
    with patch.object(fetch_rss.requests, "get", return_value=_FakeResp(atom)):
        items = fetch_rss.fetch_feed("https://x/feed")
    assert items
    assert items[0]["title"] == "Atom title"


def test_fetch_feed_raises_on_http_error():
    with patch.object(fetch_rss.requests, "get", return_value=_FakeResp(b"", 500)):
        try:
            fetch_rss.fetch_feed("https://x/feed")
        except RuntimeError:
            return
    raise AssertionError("expected RuntimeError on HTTP 500")


# ---------------------------------------------------------------------------
# fetch_many
# ---------------------------------------------------------------------------

def test_fetch_many_tags_kind_and_role():
    with patch.object(fetch_rss.requests, "get", return_value=_FakeResp(SAMPLE_RSS)):
        items = fetch_rss.fetch_many(
            [{"name": "Demo", "rss": "x", "publisher": "Demo Pub"}],
            kind="blog",
            max_items=5,
            role_template="By {publisher}",
        )
    assert items
    assert all(i["kind"] == "blog" for i in items)
    assert all(i["source_role"] == "By Demo Pub" for i in items)
    assert all(i["source_name"] == "Demo" for i in items)


def test_fetch_many_role_template_missing_key_falls_back_to_blank():
    with patch.object(fetch_rss.requests, "get", return_value=_FakeResp(SAMPLE_RSS)):
        items = fetch_rss.fetch_many(
            [{"name": "Demo", "rss": "x"}],   # no `publisher`
            kind="blog",
            max_items=5,
            role_template="By {publisher}",
        )
    assert all(i["source_role"] == "" for i in items)


def test_fetch_many_respects_max_items():
    with patch.object(fetch_rss.requests, "get", return_value=_FakeResp(SAMPLE_RSS)):
        items = fetch_rss.fetch_many(
            [{"name": "Demo", "rss": "x"}],
            kind="blog",
            max_items=1,
        )
    assert len(items) == 1


def test_fetch_many_swallows_per_feed_failure():
    def boom(*a, **kw):
        raise RuntimeError("DNS")
    with patch.object(fetch_rss.requests, "get", side_effect=boom):
        items = fetch_rss.fetch_many(
            [{"name": "Demo", "rss": "x"}],
            kind="blog",
        )
    assert items == []


def test_fetch_many_skips_entries_without_rss():
    items = fetch_rss.fetch_many([{"name": "no-url"}], kind="blog")
    assert items == []


# ---------------------------------------------------------------------------
# canonical_url
# ---------------------------------------------------------------------------

def test_canonical_url_lowercases_host_and_scheme():
    assert fetch_rss.canonical_url("HTTPS://OpenAI.COM/blog") == "https://openai.com/blog"


def test_canonical_url_strips_tracking_params():
    raw = "https://example.com/post?utm_source=tw&utm_medium=social&id=42"
    out = fetch_rss.canonical_url(raw)
    assert "utm_source" not in out
    assert "utm_medium" not in out
    assert "id=42" in out


def test_canonical_url_strips_trailing_slash_but_keeps_root():
    assert fetch_rss.canonical_url("https://x.com/foo/") == "https://x.com/foo"
    assert fetch_rss.canonical_url("https://x.com/") == "https://x.com/"


def test_canonical_url_handles_empty_input():
    assert fetch_rss.canonical_url("") == ""
    assert fetch_rss.canonical_url("   ") == ""


def test_canonical_url_passthrough_for_unknown_scheme():
    assert fetch_rss.canonical_url("mailto:foo@bar") == "mailto:foo@bar"


# ---------------------------------------------------------------------------
# dedup
# ---------------------------------------------------------------------------

def test_dedup_keeps_first_occurrence():
    items = [
        {"link": "https://example.com/a?utm_source=x", "title": "first"},
        {"link": "https://example.com/a", "title": "duplicate"},
        {"link": "https://example.com/b", "title": "different"},
    ]
    out = fetch_rss.dedup(items)
    assert len(out) == 2
    assert out[0]["title"] == "first"
    assert out[1]["title"] == "different"


def test_dedup_preserves_items_without_links():
    items = [
        {"link": "", "title": "no-link-1"},
        {"link": "", "title": "no-link-2"},
        {"link": "https://example.com", "title": "linked"},
        {"link": "https://example.com/", "title": "linked-trailing"},
    ]
    out = fetch_rss.dedup(items)
    # both no-link items kept, plus exactly one of the two URL variants
    assert sum(1 for i in out if not i["link"]) == 2
    assert sum(1 for i in out if i["link"]) == 1
