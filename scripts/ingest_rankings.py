#!/usr/bin/env python3
"""B. ingest_rankings — Product Hunt public + CSV uploads."""
from __future__ import annotations

import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from scripts.lib.paths import DATA_DIR, RAW_DIR, UPLOADS_DIR, FIXTURES_DIR, hk_now_iso
from scripts.lib.raw_retention import prune_raw_older_than_days
from scripts.lib.runs import finish_run, start_run

RANKINGS_DAILY_PATH = DATA_DIR / "rankings_daily.json"
DELTA_PATH = DATA_DIR / "rankings_delta.json"
SOURCE_VERSION = "producthunt-atom-feed-v1"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def date_stamp_hk() -> str:
    hk = timezone(timedelta(hours=8))
    return datetime.now(hk).strftime("%Y%m%d")


def signal_note(rank_delta: int | None, rank_prev: int | None) -> str:
    if rank_prev is None:
        return "新进榜"
    if rank_delta is None:
        return "持平"
    if rank_delta < 0:
        return f"排名上升 {abs(rank_delta)} 位"
    if rank_delta > 0:
        return f"排名下降 {rank_delta} 位"
    return "持平"


def fetch_product_hunt_posts(limit: int = 30) -> list[dict[str, Any]]:
    """Fetch recent launches from Product Hunt public Atom feed (no login)."""
    url = "https://www.producthunt.com/feed"
    headers = {
        "User-Agent": "DemandRadar/1.0 (+https://github.com/gaopfEditer/requirement-trendradar)",
        "Accept": "application/atom+xml",
    }
    resp = requests.get(url, headers=headers, timeout=45)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    entries = root.findall("atom:entry", ATOM_NS)
    if not entries:
        raise RuntimeError("Product Hunt feed has no entries")
    items: list[dict[str, Any]] = []
    for idx, entry in enumerate(entries[:limit], start=1):
        title_el = entry.find("atom:title", ATOM_NS)
        name = (title_el.text or "").strip() if title_el is not None else "unknown"
        link_el = entry.find("atom:link[@rel='alternate']", ATOM_NS)
        if link_el is None:
            link_el = entry.find("atom:link", ATOM_NS)
        url_p = link_el.get("href", "") if link_el is not None else ""
        items.append(
            {
                "name": name,
                "url": url_p,
                "source": "product_hunt",
                "rank_now": idx,
                "category_tags": [],
                "fetched_at": hk_now_iso(),
            }
        )
    return items


def load_csv_uploads() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(UPLOADS_DIR.glob("rankings*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("name") or row.get("product") or "").strip()
                if not name:
                    continue
                rank_now = int(row.get("rank_now") or row.get("rank") or 0) or None
                items.append(
                    {
                        "name": name,
                        "url": (row.get("url") or "").strip(),
                        "source": row.get("source") or f"csv:{path.name}",
                        "rank_now": rank_now,
                        "category_tags": [t.strip() for t in (row.get("category_tags") or row.get("tags") or "").split("|") if t.strip()],
                        "fetched_at": hk_now_iso(),
                    }
                )
    return items


def load_demo_rankings() -> list[dict]:
    path = FIXTURES_DIR / "rankings_demo.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["items"]
    return []


def compute_delta(today: list[dict], yesterday_items: list[dict]) -> list[dict]:
    prev_by_key: dict[str, int] = {}
    for it in yesterday_items:
        key = f"{it.get('source')}::{it.get('name')}"
        if it.get("rank_now") is not None:
            prev_by_key[key] = int(it["rank_now"])

    delta_items: list[dict] = []
    for it in today:
        key = f"{it.get('source')}::{it.get('name')}"
        rank_now = it.get("rank_now")
        rank_prev = prev_by_key.get(key)
        rank_delta = None
        if rank_now is not None and rank_prev is not None:
            rank_delta = int(rank_now) - int(rank_prev)
        out = {**it, "rank_prev": rank_prev, "rank_delta": rank_delta}
        out["signal_note"] = signal_note(rank_delta, rank_prev)
        delta_items.append(out)
    # New entries not in yesterday
    today_keys = {f"{it.get('source')}::{it.get('name')}" for it in today}
    for key, rank_prev in prev_by_key.items():
        if key not in today_keys:
            source, name = key.split("::", 1)
            delta_items.append(
                {
                    "name": name,
                    "url": "",
                    "source": source,
                    "rank_now": None,
                    "rank_prev": rank_prev,
                    "rank_delta": None,
                    "category_tags": [],
                    "signal_note": "掉出榜",
                    "fetched_at": hk_now_iso(),
                }
            )
    return delta_items


def load_yesterday_items() -> list[dict]:
    hk = timezone(timedelta(hours=8))
    yesterday = (datetime.now(hk) - timedelta(days=1)).strftime("%Y%m%d")
    path = RAW_DIR / f"rankings_{yesterday}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")).get("items", [])
    if RANKINGS_DAILY_PATH.exists():
        return json.loads(RANKINGS_DAILY_PATH.read_text(encoding="utf-8")).get("items", [])
    return []


def run(demo: bool = False, csv_only: bool = False) -> int:
    run_id = start_run(
        "ingest_rankings",
        {"source": "demo" if demo else ("csv" if csv_only else "product_hunt+csv"), "version": SOURCE_VERSION},
    )
    stamp = date_stamp_hk()
    raw_path = RAW_DIR / f"rankings_{stamp}.json"
    source_errors: list[str] = []
    items: list[dict] = []

    try:
        if demo:
            items = load_demo_rankings()
            if not items:
                raise RuntimeError("demo fixtures missing")
        else:
            if not csv_only:
                try:
                    items.extend(fetch_product_hunt_posts())
                except Exception as exc:  # noqa: BLE001
                    source_errors.append(f"product_hunt: {exc}")
            csv_items = load_csv_uploads()
            items.extend(csv_items)

        if not items:
            msg = "No ranking data from Product Hunt or CSV"
            if source_errors:
                msg += "; " + "; ".join(source_errors)
            raw_path.write_text(
                json.dumps({"run_id": run_id, "items": [], "errors": source_errors}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            finish_run(run_id, "failed", counts={"items": 0}, error=msg, meta={"csv_fallback": True})
            return 1

        yesterday = load_yesterday_items()
        delta = compute_delta(items, yesterday)

        raw_doc = {
            "run_id": run_id,
            "fetched_at": hk_now_iso(),
            "source_version": SOURCE_VERSION,
            "items": items,
            "errors": source_errors,
        }
        raw_path.write_text(json.dumps(raw_doc, ensure_ascii=False, indent=2), encoding="utf-8")

        daily = {
            "updated_at": hk_now_iso(),
            "date_stamp": stamp,
            "run_id": run_id,
            "items": items,
            "errors": source_errors,
        }
        RANKINGS_DAILY_PATH.write_text(json.dumps(daily, ensure_ascii=False, indent=2), encoding="utf-8")
        DELTA_PATH.write_text(
            json.dumps({"updated_at": hk_now_iso(), "items": delta}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        prune_raw_older_than_days(30)

        status = "success" if not source_errors else "partial"
        finish_run(
            run_id,
            status,
            counts={"items": len(items), "delta": len(delta)},
            error="; ".join(source_errors) if source_errors else None,
            meta={"used_csv": bool(load_csv_uploads()), "ph_failed": bool(source_errors)},
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        finish_run(run_id, "failed", error=str(exc))
        return 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--csv-only", action="store_true")
    args = parser.parse_args()
    sys.exit(run(demo=args.demo, csv_only=args.csv_only))


if __name__ == "__main__":
    main()
