"""Tests for 3-hour segment archive helpers."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import archive_data
import segment_window


def _payload(start: str, end: str, title: str) -> dict:
    return {
        "schema_version": 1,
        "generated_at": end,
        "window": {"start": start, "end": end},
        "counts": {"x": 1, "blogs": 0, "podcasts": 0, "releases": 0, "videos": 0},
        "items": {
            "x": [
                {
                    "kind": "x",
                    "source_name": "Sam Altman",
                    "source_handle": "sama",
                    "source_role": "CEO, OpenAI",
                    "title": title,
                    "summary": title,
                    "link": f"https://x.com/sama/status/{title}",
                    "published": start,
                }
            ],
            "blogs": [],
            "podcasts": [],
            "releases": [],
            "videos": [],
        },
    }


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_latest_complete_window_uses_previous_three_hour_bucket():
    now = datetime(2026, 5, 21, 10, 17, tzinfo=ZoneInfo("Asia/Shanghai"))

    start, end = segment_window.latest_complete_window(now)

    assert start.isoformat() == "2026-05-21T06:00:00+08:00"
    assert end.isoformat() == "2026-05-21T09:00:00+08:00"


def test_archive_builds_index_and_daily_for_complete_day(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    dist_dir = tmp_path / "dist"
    day = "2026-05-21"
    for hour in archive_data.SEGMENT_HOURS:
        start = f"{day}T{hour}:00:00+00:00"
        end_hour = (int(hour) + 3) % 24
        end_day = day if hour != "21" else "2026-05-22"
        end = f"{end_day}T{end_hour:02d}:00:00+00:00"
        _write(data_dir / "segments" / day / f"{hour}.json", _payload(start, end, hour))

    monkeypatch.setattr(archive_data, "ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sources.json").write_text('{"site": {}}', encoding="utf-8")

    archive_data.merge_complete_daily(data_dir)
    index = archive_data.build_index(data_dir)
    archive_data.copy_data_to_dist(data_dir, dist_dir)

    assert (data_dir / "daily" / f"{day}.json").exists()
    assert (data_dir / "index.json").exists()
    assert len(index["segments"]) == 8
    assert len(index["daily"]) == 1
    assert (dist_dir / "data" / "index.json").exists()
