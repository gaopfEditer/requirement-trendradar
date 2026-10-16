from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.lib.paths import DATA_DIR, hk_now_iso8601, parse_updated_at_to_iso

META_PATH = DATA_DIR / "meta.json"
OPPORTUNITIES_PATH = DATA_DIR / "opportunities.json"
TRENDS_PATH = DATA_DIR / "trends_daily.json"
RUNS_PATH = DATA_DIR / "runs.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_meta() -> dict[str, Any]:
    opportunities = _read_json(OPPORTUNITIES_PATH)
    trends = _read_json(TRENDS_PATH)
    runs_doc = _read_json(RUNS_PATH)
    runs = runs_doc.get("runs") or []

    updated_raw = opportunities.get("updated_at") or runs_doc.get("last_updated")
    updated_at = parse_updated_at_to_iso(updated_raw) or hk_now_iso8601()

    last_publish = next((r for r in runs if r.get("step") == "publish_site"), None)
    last_run_id = last_publish.get("run_id") if last_publish else (runs[0].get("run_id") if runs else None)
    last_run_ok = bool(last_publish and last_publish.get("status") == "success")

    trends_source = trends.get("trends_source", "unknown")
    trends_demo_active = trends_source == "demo" or bool(trends.get("trends_fallback_demo"))

    return {
        "updated_at": updated_at,
        "schedule": "every_4h",
        "last_run_id": last_run_id,
        "last_run_ok": last_run_ok,
        "last_run_failed": not last_run_ok,
        "timezone_label": "香港",
        "trends_source": trends_source,
        "trends_demo_active": trends_demo_active,
        "published_at": hk_now_iso8601(),
        "opportunities_run_id": opportunities.get("run_id"),
    }


def write_meta() -> dict[str, Any]:
    meta = build_meta()
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta
