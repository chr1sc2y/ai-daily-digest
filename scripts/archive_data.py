"""Archive helpers for 3-hour digest segments.

The daily workflow writes one normalized segment JSON every three hours under
``data/segments/YYYY-MM-DD/HH.json``. This script keeps the static archive
usable by:

- merging complete days into ``data/daily/YYYY-MM-DD.json``;
- writing ``data/index.json`` for the frontend;
- copying the committed data tree into ``dist/data`` for GitHub Pages;
- rendering ``dist/index.html`` from the latest 24 hours of segment data.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import fetch_rss  # noqa: E402
import render_html  # noqa: E402

ROOT = HERE.parent
SEGMENT_HOURS = ("00", "03", "06", "09", "12", "15", "18", "21")
KINDS = ("x", "blogs", "podcasts", "releases", "videos")
PROVIDER_MOCK_MARKERS = (
    "From KaitoEasyAPI, a reminder:",
    "Thus, we returned N pieces of mock data",
)


def parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def item_dt(item: dict) -> datetime | None:
    return parse_dt(item.get("published"))


def jsonable_item(item: dict) -> dict:
    out = dict(item)
    published = out.get("published")
    if isinstance(published, datetime):
        out["published"] = published.astimezone(timezone.utc).isoformat()
    return out


def load_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def flatten_items(payloads: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {kind: [] for kind in KINDS}
    for payload in payloads:
        items = payload.get("items") or {}
        for kind in KINDS:
            out[kind].extend(items.get(kind) or [])
    out["x"] = dedup_by_link_or_text([item for item in out["x"] if usable_x_item(item)])
    for kind in ("blogs", "podcasts", "releases", "videos"):
        out[kind] = fetch_rss.dedup(out[kind])
    for kind in KINDS:
        out[kind] = sorted(
            out[kind],
            key=lambda item: item_dt(item) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
    return out


def usable_x_item(item: dict) -> bool:
    text = f"{item.get('title') or ''}\n{item.get('summary') or ''}"
    if any(marker in text for marker in PROVIDER_MOCK_MARKERS):
        return False
    return bool(item.get("link")) and item_dt(item) is not None


def dedup_by_link_or_text(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        link = fetch_rss.canonical_url(item.get("link", ""))
        key = link or "|".join(
            [
                str(item.get("source_handle") or ""),
                str(item.get("summary") or ""),
                str(item.get("published") or ""),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def counts(items: dict[str, list[dict]]) -> dict[str, int]:
    return {kind: len(items[kind]) for kind in KINDS}


def segment_paths_for_day(data_dir: Path, day: str) -> list[Path]:
    base = data_dir / "segments" / day
    return [base / f"{hour}.json" for hour in SEGMENT_HOURS]


def merge_complete_daily(data_dir: Path) -> list[Path]:
    segments_root = data_dir / "segments"
    if not segments_root.exists():
        return []
    written: list[Path] = []
    for day_dir in sorted(p for p in segments_root.iterdir() if p.is_dir()):
        paths = segment_paths_for_day(data_dir, day_dir.name)
        if not all(path.exists() for path in paths):
            continue
        payloads = [load_payload(path) for path in paths]
        items = flatten_items(payloads)
        generated_values = [
            parse_dt(payload.get("generated_at"))
            for payload in payloads
            if payload.get("generated_at")
        ]
        generated_at = max(
            (dt for dt in generated_values if dt is not None),
            default=datetime.now(timezone.utc),
        )
        daily = {
            "schema_version": 1,
            "date": day_dir.name,
            "generated_at": generated_at.isoformat(),
            "source_segments": [path.as_posix().split("data/", 1)[-1] for path in paths],
            "counts": counts(items),
            "items": {kind: [jsonable_item(i) for i in items[kind]] for kind in KINDS},
        }
        out_path = data_dir / "daily" / f"{day_dir.name}.json"
        write_json(out_path, daily)
        written.append(out_path)
    return written


def build_index(data_dir: Path, *, tz_name: str = "Asia/Shanghai") -> dict:
    tz = ZoneInfo(tz_name)
    segments: list[dict] = []
    for path in sorted((data_dir / "segments").glob("*/*.json")):
        payload = load_payload(path)
        rel = path.as_posix().split("data/", 1)[-1]
        window = payload.get("window") or {}
        try:
            date, hour = path.parts[-2], path.stem
        except IndexError:
            date, hour = "", ""
        segments.append(
            {
                "date": date,
                "hour": hour,
                "path": f"data/{rel}",
                "window_start": window.get("start"),
                "window_end": window.get("end"),
                "counts": payload.get("counts") or {},
            }
        )

    daily: list[dict] = []
    for path in sorted((data_dir / "daily").glob("*.json")):
        payload = load_payload(path)
        rel = path.as_posix().split("data/", 1)[-1]
        daily.append(
            {
                "date": payload.get("date") or path.stem,
                "path": f"data/{rel}",
                "counts": payload.get("counts") or {},
            }
        )

    index = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": tz_name,
        "local_date": datetime.now(tz).date().isoformat(),
        "ranges": ["3h", "6h", "12h", "24h", "3d", "7d"],
        "default_range": "24h",
        "segments": segments,
        "daily": daily,
    }
    write_json(data_dir / "index.json", index)
    return index


def payloads_for_latest_hours(data_dir: Path, hours: int) -> list[dict]:
    payloads = [load_payload(path) for path in sorted((data_dir / "segments").glob("*/*.json"))]
    if not payloads:
        daily = sorted((data_dir / "daily").glob("*.json"))
        return [load_payload(daily[-1])] if daily else []

    ends = [parse_dt((payload.get("window") or {}).get("end")) for payload in payloads]
    latest_end = max((end for end in ends if end is not None), default=datetime.now(timezone.utc))
    cutoff = latest_end - timedelta(hours=hours)
    selected: list[dict] = []
    for payload in payloads:
        window = payload.get("window") or {}
        end = parse_dt(window.get("end"))
        if end is None or end > cutoff:
            selected.append(payload)
    return selected


def render_latest(data_dir: Path, dist_dir: Path, *, hours: int = 24) -> None:
    payloads = payloads_for_latest_hours(data_dir, hours)
    items = flatten_items(payloads)
    html = render_html.render(
        x_items=items["x"],
        blog_items=items["blogs"],
        podcast_items=items["podcasts"],
        release_items=items["releases"],
        video_items=items["videos"],
        site=json.loads((ROOT / "config" / "sources.json").read_text(encoding="utf-8")).get("site") or {},
        interactive=True,
    )
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text(html, encoding="utf-8")
    cname = ROOT / "CNAME"
    if cname.exists():
        shutil.copy2(cname, dist_dir / "CNAME")


def copy_data_to_dist(data_dir: Path, dist_dir: Path) -> None:
    target = dist_dir / "data"
    if target.exists():
        shutil.rmtree(target)
    if data_dir.exists():
        shutil.copytree(data_dir, target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build digest data archive and site.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument("--render-hours", type=int, default=24)
    args = parser.parse_args(argv)

    merge_complete_daily(args.data_dir)
    build_index(args.data_dir, tz_name=args.timezone)
    render_latest(args.data_dir, args.dist_dir, hours=args.render_hours)
    copy_data_to_dist(args.data_dir, args.dist_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
