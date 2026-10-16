#!/usr/bin/env python3
"""E. build_weekly_movers — weekly keyword & product movers (Monday HKT or fixture)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.lib.paths import (
    CONFIG_DIR,
    DATA_DIR,
    RAW_DIR,
    FIXTURES_DIR,
    HK,
    hk_now,
    hk_now_iso8601,
    iso_week_label,
)
from scripts.lib.runs import finish_run, start_run

WEEKLY_PATH = DATA_DIR / "weekly_movers.json"
TOP_N = 10
DATE_RE = re.compile(r"trends_(\d{8})\.json$")
RANK_DATE_RE = re.compile(r"rankings_(\d{8})\.json$")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_stamp(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y%m%d").replace(tzinfo=HK)


def list_dated_raw(pattern: str, regex: re.Pattern[str]) -> list[tuple[datetime, Path]]:
    out: list[tuple[datetime, Path]] = []
    for path in RAW_DIR.glob(pattern):
        m = regex.search(path.name)
        if not m:
            continue
        out.append((_parse_stamp(m.group(1)), path))
    out.sort(key=lambda x: x[0])
    return out


def pick_snapshot(snaps: list[tuple[datetime, Path]], target: datetime) -> Path | None:
    if not snaps:
        return None
    before = [s for s in snaps if s[0] <= target]
    if before:
        return before[-1][1]
    return snaps[0][1]


def index_trends_items(doc: dict[str, Any], default_geo: str) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for it in doc.get("items") or []:
        key = f"{it.get('keyword')}::{it.get('geo', default_geo)}"
        if it.get("geo") == default_geo or key not in indexed:
            indexed[key] = it
    return indexed


def trends_demo_dominated() -> bool:
    trends_path = DATA_DIR / "trends_daily.json"
    if not trends_path.exists():
        return False
    doc = _load_json(trends_path)
    if doc.get("trends_source") == "demo":
        return True
    demo_snaps = 0
    total = 0
    for _, path in list_dated_raw("trends_*.json", DATE_RE)[-14:]:
        raw = _load_json(path)
        total += 1
        if raw.get("trends_source") == "demo":
            demo_snaps += 1
    return total > 0 and demo_snaps >= max(2, total // 2)


def build_keywords(default_geo: str) -> list[dict[str, Any]]:
    snaps = list_dated_raw("trends_*.json", DATE_RE)
    if len(snaps) < 2:
        return []
    now = hk_now()
    latest_path = snaps[-1][1]
    prev_target = now - timedelta(days=7)
    prev_path = pick_snapshot(snaps, prev_target)
    if prev_path is None or prev_path == latest_path:
        return []

    latest = index_trends_items(_load_json(latest_path), default_geo)
    prev = index_trends_items(_load_json(prev_path), default_geo)
    demo_bad = trends_demo_dominated()
    rows: list[dict[str, Any]] = []

    seeds = json.loads((CONFIG_DIR / "seeds.json").read_text(encoding="utf-8"))
    for entry in seeds.get("keywords", []):
        kw = entry["keyword"]
        key = f"{kw}::{default_geo}"
        cur = latest.get(key)
        old = prev.get(key)
        if not cur or not old:
            continue
        interest_now = int(cur.get("interest_now") or 0)
        interest_prev = int(old.get("interest_now") or 0)
        growth = interest_now - interest_prev
        disqualified = demo_bad
        rows.append(
            {
                "keyword": kw,
                "geo": default_geo,
                "track": entry.get("track"),
                "interest_now": interest_now,
                "interest_prev": interest_prev,
                "delta": growth,
                "growth_score": growth,
                "pay_intent_score": cur.get("pay_intent_score", 0),
                "slope_90d": cur.get("slope_90d"),
                "disqualified_demo": disqualified,
            }
        )

    rows = [r for r in rows if not r["disqualified_demo"]]
    rows.sort(key=lambda r: (-r["growth_score"], -(r.get("pay_intent_score") or 0)))
    for i, row in enumerate(rows[:TOP_N], start=1):
        row["rank"] = i
    return rows[:TOP_N]


def build_apps() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    delta_path = DATA_DIR / "rankings_delta.json"
    if not delta_path.exists():
        return [], []
    delta_doc = _load_json(delta_path)
    items = delta_doc.get("items") or []

    movers: list[dict[str, Any]] = []
    new_entries: list[dict[str, Any]] = []

    for it in items:
        name = it.get("name") or ""
        if not name:
            continue
        rank_delta = it.get("rank_delta")
        is_new = it.get("rank_prev") is None and it.get("rank_now") is not None
        row = {
            "name": name,
            "url": it.get("url") or "",
            "source": it.get("source") or "",
            "rank_now": it.get("rank_now"),
            "rank_prev": it.get("rank_prev"),
            "rank_delta": rank_delta,
            "growth_score": -(rank_delta) if rank_delta is not None else None,
            "signal_note": it.get("signal_note"),
            "new_entry": is_new,
        }
        if is_new:
            new_entries.append(row)
        elif rank_delta is not None and rank_delta < 0:
            movers.append(row)

    movers.sort(key=lambda r: (-(r["growth_score"] or 0), r.get("rank_now") or 999))
    for i, row in enumerate(movers[:TOP_N], start=1):
        row["rank"] = i
    new_entries = new_entries[:TOP_N]
    for i, row in enumerate(new_entries, start=1):
        row["rank"] = i
    return movers[:TOP_N], new_entries


def load_fixture() -> dict[str, Any]:
    path = FIXTURES_DIR / "weekly_movers_demo.json"
    if not path.exists():
        raise FileNotFoundError("fixtures/weekly_movers_demo.json missing")
    return _load_json(path)


def should_compute() -> bool:
    now = hk_now()
    is_monday = now.weekday() == 0
    snaps = list_dated_raw("trends_*.json", DATE_RE)
    if len(snaps) < 2:
        return False
    oldest, newest = snaps[0][0], snaps[-1][0]
    span = (newest - oldest).days
    return is_monday or span >= 6


def run(force_fixture: bool = False) -> int:
    run_id = start_run("build_weekly_movers", {})
    try:
        seeds = json.loads((CONFIG_DIR / "seeds.json").read_text(encoding="utf-8"))
        default_geo = seeds.get("default_geo", "US")
        now = hk_now()

        if force_fixture or not should_compute():
            doc = load_fixture()
            doc["source"] = "fixture"
            doc.setdefault("week", iso_week_label(now))
            doc.setdefault("generated_at", hk_now_iso8601())
            if not should_compute():
                doc["skipped"] = "insufficient_history"
        else:
            keywords = build_keywords(default_geo)
            apps, new_entries = build_apps()
            doc = {
                "week": iso_week_label(now),
                "generated_at": hk_now_iso8601(),
                "source": "computed",
                "timezone_label": "香港",
                "keywords_top": keywords,
                "apps_top": apps,
                "new_entries": new_entries,
                "skipped": None if keywords or apps else "insufficient_history",
            }
            if not keywords and not apps:
                fixture = load_fixture()
                doc["keywords_top"] = fixture.get("keywords_top", [])
                doc["apps_top"] = fixture.get("apps_top", [])
                doc["new_entries"] = fixture.get("new_entries", [])
                doc["source"] = "fixture"
                doc["skipped"] = "insufficient_history"

        WEEKLY_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        week_slug = doc.get("week", iso_week_label(now)).replace("-", "")
        raw_weekly = RAW_DIR / f"weekly_{week_slug}.json"
        raw_weekly.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

        finish_run(
            run_id,
            "success",
            counts={
                "keywords": len(doc.get("keywords_top") or []),
                "apps": len(doc.get("apps_top") or []),
                "new_entries": len(doc.get("new_entries") or []),
            },
            meta={"source": doc.get("source"), "week": doc.get("week")},
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        finish_run(run_id, "failed", error=str(exc))
        return 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", action="store_true", help="Force fixture output")
    args = parser.parse_args()
    sys.exit(run(force_fixture=args.fixture))


if __name__ == "__main__":
    main()
