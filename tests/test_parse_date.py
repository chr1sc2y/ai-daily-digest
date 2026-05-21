"""Unit tests for fetch_x._parse_date and fetch_podcasts dating logic."""
from __future__ import annotations

from datetime import datetime, timezone

import fetch_x


def test_parse_date_with_timezone():
    dt = fetch_x._parse_date("2026-05-20T12:00:00+02:00")
    assert dt is not None
    assert dt.tzinfo is not None
    # 12:00 in +02:00 is 10:00 UTC
    assert dt.astimezone(timezone.utc) == datetime(
        2026, 5, 20, 10, 0, 0, tzinfo=timezone.utc
    )


def test_parse_date_naive_assumes_utc():
    dt = fetch_x._parse_date("2026-05-20 12:00:00")
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt == datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_parse_date_handles_rfc822():
    dt = fetch_x._parse_date("Wed, 20 May 2026 12:00:00 GMT")
    assert dt is not None
    assert dt.astimezone(timezone.utc).date() == datetime(2026, 5, 20).date()


def test_parse_date_returns_none_for_empty():
    assert fetch_x._parse_date("") is None
    assert fetch_x._parse_date(None) is None


def test_parse_date_returns_none_for_garbage():
    assert fetch_x._parse_date("not a date at all") is None
