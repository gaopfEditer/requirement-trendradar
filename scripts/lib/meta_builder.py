from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.lib.paths import DATA_DIR, hk_now_iso8601, parse_updated_at_to_iso

META_PATH = DATA_DIR / "meta.json"
OPPORTUNITIES_PATH = DATA_DIR / "opportunities.json"
JOB_LEADS_PATH = DATA_DIR / "job_leads.json"
TRENDS_PATH = DATA_DIR / "trends_daily.json"
RUNS_PATH = DATA_DIR / "runs.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_meta() -> dict[str, Any]:
    opportunities = _read_json(OPPORTUNITIES_PATH)
    job_leads = _read_json(JOB_LEADS_PATH)
    trends = _read_json(TRENDS_PATH)
    runs_doc = _read_json(RUNS_PATH)
    runs = runs_doc.get("runs") or []
    last_job_ingest = next((r for r in runs if r.get("step") == "ingest_job_leads"), None)

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
        "job_leads_updated_at": parse_updated_at_to_iso(job_leads.get("updated_at"))
        or job_leads.get("updated_at"),
        "job_leads_count": len(job_leads.get("jobs") or []),
        "job_leads_recommend_count": sum(
            1 for j in (job_leads.get("jobs") or []) if j.get("recommend")
        ),
        "job_leads_run_id": job_leads.get("run_id"),
        "fiverr_skipped": bool((job_leads.get("ingest") or {}).get("fiverr", {}).get("skipped")),
        "fiverr_skip_reason": (job_leads.get("ingest") or {}).get("fiverr", {}).get("reason"),
        "last_job_ingest_ok": bool(last_job_ingest and last_job_ingest.get("status") == "success"),
    }


def write_meta() -> dict[str, Any]:
    meta = build_meta()
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta
