"""Compute the latest complete 3-hour Asia/Shanghai digest segment."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def latest_complete_window(now: datetime, *, hours: int = 3) -> tuple[datetime, datetime]:
    bucket_hour = (now.hour // hours) * hours
    end = now.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=hours)
    return start, end


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit GitHub Actions env vars for a digest segment.")
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument("--hours", type=int, default=3)
    parser.add_argument("--github-env", help="Path to $GITHUB_ENV.")
    args = parser.parse_args()

    tz = ZoneInfo(args.timezone)
    start_local, end_local = latest_complete_window(datetime.now(tz), hours=args.hours)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    values = {
        "DIGEST_WINDOW_START": start_utc.isoformat(),
        "DIGEST_WINDOW_END": end_utc.isoformat(),
        "DIGEST_SEGMENT_DATE": start_local.date().isoformat(),
        "DIGEST_SEGMENT_HOUR": f"{start_local.hour:02d}",
        "DIGEST_SEGMENT_PATH": f"data/segments/{start_local.date().isoformat()}/{start_local.hour:02d}.json",
    }
    lines = [f"{key}={value}" for key, value in values.items()]
    if args.github_env:
        with open(args.github_env, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
