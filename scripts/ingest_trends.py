#!/usr/bin/env python3
"""A. ingest_trends — fetch Google Trends for configured seeds."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.lib.paths import CONFIG_DIR, DATA_DIR, RAW_DIR, FIXTURES_DIR, hk_now_iso
from scripts.lib.pay_intent import pay_intent_score
from scripts.lib.raw_retention import prune_raw_older_than_days
from scripts.lib.runs import finish_run, start_run
from scripts.lib.trends_math import slope_from_series

TRENDS_DAILY_PATH = DATA_DIR / "trends_daily.json"
SOURCE_VERSION = "pytrends-4.9"


def load_seeds() -> dict:
    return json.loads((CONFIG_DIR / "seeds.json").read_text(encoding="utf-8"))


def date_stamp_hk() -> str:
    hk = timezone(timedelta(hours=8))
    return datetime.now(hk).strftime("%Y%m%d")


def fetch_pytrends(keyword: str, geo: str, timeframe: str) -> dict:
    from pytrends.request import TrendReq

    tr = TrendReq(hl="en-US", tz=360, retries=2, backoff_factor=0.5)
    tr.build_payload([keyword], timeframe=timeframe, geo=geo)
    iot = tr.interest_over_time()
    related = tr.related_queries()
    series: list[int] = []
    if iot is not None and not iot.empty and keyword in iot.columns:
        series = [int(x) for x in iot[keyword].tolist() if x == x]
    rising: list[str] = []
    if related and keyword in related and related[keyword].get("rising") is not None:
        df = related[keyword]["rising"]
        if df is not None and not df.empty:
            col = "query" if "query" in df.columns else df.columns[0]
            rising = [str(x) for x in df[col].head(10).tolist()]
    return {"series": series, "related_queries": rising}


def load_demo_trends() -> list[dict]:
    path = FIXTURES_DIR / "trends_demo.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["items"]
    return []


def run(demo: bool = False, geos_override: list[str] | None = None) -> int:
    run_id = start_run("ingest_trends", {"source": "demo" if demo else "pytrends", "version": SOURCE_VERSION})
    seeds = load_seeds()
    stamp = date_stamp_hk()
    raw_path = RAW_DIR / f"trends_{stamp}.json"
    items: list[dict] = []
    errors: list[str] = []

    primary_days = seeds.get("window_primary_days", 90)
    timeframe = f"today {primary_days}-d"
    geos = geos_override or [seeds.get("default_geo", "US")]
    if geos_override is None and seeds.get("fetch_additional_geos"):
        geos = geos + list(seeds.get("additional_geos", []))

    try:
        if demo:
            items = load_demo_trends()
            if not items:
                raise RuntimeError("demo mode but fixtures/trends_demo.json missing or empty")
        else:
            kw_entries = seeds["keywords"]
            for entry in kw_entries:
                keyword = entry["keyword"]
                track = entry.get("track", "未分类")
                for geo in geos:
                    try:
                        fetched = fetch_pytrends(keyword, geo, timeframe)
                        slope_label, slope_delta = slope_from_series(fetched["series"])
                        interest_now = fetched["series"][-1] if fetched["series"] else 0
                        related = fetched["related_queries"]
                        items.append(
                            {
                                "keyword": keyword,
                                "track": track,
                                "geo": geo,
                                "window": f"{primary_days}d",
                                "interest_now": interest_now,
                                "slope_90d": slope_label,
                                "slope_delta_est": round(slope_delta, 2),
                                "related_queries": related,
                                "pay_intent_score": pay_intent_score(keyword, related),
                                "pay_intent_est": True,
                                "fetched_at": hk_now_iso(),
                            }
                        )
                        time.sleep(1.2)
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{keyword}@{geo}: {exc}")

        trends_source = "demo" if demo else "live"
        raw_doc = {
            "run_id": run_id,
            "fetched_at": hk_now_iso(),
            "source_version": SOURCE_VERSION,
            "trends_source": trends_source,
            "items": items,
            "errors": errors,
        }
        raw_path.write_text(json.dumps(raw_doc, ensure_ascii=False, indent=2), encoding="utf-8")

        daily = {
            "updated_at": hk_now_iso(),
            "date_stamp": stamp,
            "run_id": run_id,
            "trends_source": trends_source,
            "items": items,
            "errors": errors,
        }
        TRENDS_DAILY_PATH.write_text(json.dumps(daily, ensure_ascii=False, indent=2), encoding="utf-8")
        prune_raw_older_than_days(30)

        if not items and errors:
            finish_run(run_id, "failed", counts={"items": 0}, error="; ".join(errors[:5]))
            return 1
        status = "success" if not errors else "partial"
        finish_run(
            run_id,
            status,
            counts={"items": len(items), "errors": len(errors), "geos": len(geos)},
            error="; ".join(errors[:3]) if errors else None,
        )
        return 0 if status == "success" else 0
    except Exception as exc:  # noqa: BLE001
        finish_run(run_id, "failed", error=str(exc))
        return 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Use fixture data (offline)")
    args = parser.parse_args()
    sys.exit(run(demo=args.demo))


if __name__ == "__main__":
    main()
