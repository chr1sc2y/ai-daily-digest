"""Unit tests for the podcast fetcher (RSS parsing + leader filter)."""
from __future__ import annotations

import textwrap
from unittest.mock import patch

import fetch_podcasts
import fetch_rss


LEADERS = [
    {"name": "Sam Altman", "handle": "sama"},
    {"name": "Andrej Karpathy", "handle": "karpathy"},
    {"name": "Elon Musk", "handle": "elonmusk"},
]


# ---------------------------------------------------------------------------
# _build_keywords / _matched_leader
# ---------------------------------------------------------------------------

def test_build_keywords_includes_full_name_last_name_handle():
    patterns = fetch_podcasts._build_keywords(LEADERS)
    names = [n for n, _ in patterns]
    assert names == ["Sam Altman", "Andrej Karpathy", "Elon Musk"]

    # Should match by full name
    assert fetch_podcasts._matched_leader("a chat with Sam Altman today", patterns) == "Sam Altman"
    # Should match by last name (>3 chars)
    assert fetch_podcasts._matched_leader("Karpathy explains llm.c", patterns) == "Andrej Karpathy"
    # Should match by handle
    assert fetch_podcasts._matched_leader("hosted by @sama", patterns) == "Sam Altman"
    # Case-insensitive
    assert fetch_podcasts._matched_leader("ELON musk on rockets", patterns) == "Elon Musk"


def test_matched_leader_returns_none_for_non_match():
    patterns = fetch_podcasts._build_keywords(LEADERS)
    assert fetch_podcasts._matched_leader("nothing relevant here", patterns) is None
    assert fetch_podcasts._matched_leader("", patterns) is None


def test_build_keywords_skips_short_last_names():
    # "Wu" is < 4 chars so it should NOT be added as a separate term, but the
    # full name "Pat Wu" still matches.
    patterns = fetch_podcasts._build_keywords([{"name": "Pat Wu", "handle": "pwu"}])
    assert fetch_podcasts._matched_leader("Pat Wu spoke today", patterns) == "Pat Wu"
    # bare "Wu" should NOT match (it's a too-common short token)
    assert fetch_podcasts._matched_leader("the band Wu-Tang Clan", patterns) is None


# ---------------------------------------------------------------------------
# _fetch_feed (with stubbed requests)
# ---------------------------------------------------------------------------

SAMPLE_RSS = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Demo Podcast</title>
        <item>
          <title>Talking to Sam Altman</title>
          <description>OpenAI deep dive with Sam Altman</description>
          <link>https://example.com/ep1</link>
          <pubDate>Mon, 19 May 2026 09:00:00 GMT</pubDate>
          <author>host@example.com (Demo Host)</author>
        </item>
        <item>
          <title>Random topic</title>
          <description>Nothing AI here</description>
          <link>https://example.com/ep2</link>
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


def test_fetch_feed_extracts_items():
    with patch.object(fetch_rss.requests, "get", return_value=_FakeResp(SAMPLE_RSS)):
        items = fetch_podcasts._fetch_feed("https://example.com/feed")

    assert len(items) == 2
    assert items[0]["title"] == "Talking to Sam Altman"
    assert items[0]["link"] == "https://example.com/ep1"
    assert items[0]["published"] is not None
    assert items[0]["published"].tzinfo is not None
    assert items[0]["kind"] == "podcast"


# ---------------------------------------------------------------------------
# fetch_all (high-level filtering)
# ---------------------------------------------------------------------------

def test_fetch_all_filters_by_leader_and_attaches_metadata():
    with patch.object(fetch_rss.requests, "get", return_value=_FakeResp(SAMPLE_RSS)):
        out = fetch_podcasts.fetch_all(
            podcasts=[{"name": "Demo Podcast", "rss": "x", "host": "Demo Host"}],
            leaders=LEADERS,
            max_items=5,
            require_leader_match=True,
        )

    assert len(out) == 1
    assert out[0]["title"] == "Talking to Sam Altman"
    assert out[0]["source_name"] == "Demo Podcast"
    assert out[0]["source_role"] == "Featuring Sam Altman"
    assert out[0]["source_handle"] == "Demo Podcast"


def test_fetch_all_keeps_everything_when_filter_disabled():
    with patch.object(fetch_rss.requests, "get", return_value=_FakeResp(SAMPLE_RSS)):
        out = fetch_podcasts.fetch_all(
            podcasts=[{"name": "Demo Podcast", "rss": "x", "host": "Demo Host"}],
            leaders=LEADERS,
            max_items=5,
            require_leader_match=False,
        )
    assert len(out) == 2
    # Episodes that don't match a leader fall back to "Hosted by ..."
    assert any(i["source_role"] == "Hosted by Demo Host" for i in out)


def test_fetch_all_swallows_per_feed_failure():
    def boom(url, headers=None, timeout=None):
        raise RuntimeError("DNS failure")

    with patch.object(fetch_rss.requests, "get", side_effect=boom):
        out = fetch_podcasts.fetch_all(
            podcasts=[{"name": "Broken", "rss": "x"}],
            leaders=LEADERS,
        )
    assert out == []


def test_fetch_all_respects_max_items():
    # Build a feed with many leader-matching items
    items_xml = "".join(
        textwrap.dedent(f"""\
        <item>
          <title>Sam Altman talks #{i}</title>
          <description>x</description>
          <link>https://example.com/{i}</link>
          <pubDate>Mon, 19 May 2026 09:00:00 GMT</pubDate>
        </item>
        """)
        for i in range(20)
    )
    big = (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        + items_xml
        + "</channel></rss>"
    ).encode("utf-8")

    with patch.object(fetch_rss.requests, "get", return_value=_FakeResp(big)):
        out = fetch_podcasts.fetch_all(
            podcasts=[{"name": "Demo", "rss": "x"}],
            leaders=LEADERS,
            max_items=4,
        )
    assert len(out) == 4
