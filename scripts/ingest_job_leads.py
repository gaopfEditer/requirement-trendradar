#!/usr/bin/env python3
"""Ingest open Freelancer / Fiverr job leads (public only, no login)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from typing import Any
from urllib.parse import quote

import requests

from scripts.lib.dual_track_screen import screen_job, sort_results
from scripts.lib.job_lead_cards import merge_recommended_into_opportunities
from scripts.lib.paths import CONFIG_DIR, DATA_DIR, PUBLIC_DATA_DIR, hk_now_iso
from scripts.lib.runs import finish_run, start_run

JOB_LEADS_PATH = DATA_DIR / "job_leads.json"
SEEDS_PATH = CONFIG_DIR / "seeds.json"
FREELANCER_API = "https://www.freelancer.com/api/projects/0.1/projects/all/"
USER_AGENT = "DemandRadar/1.0 (+https://github.com/gaopfEditer/requirement-trendradar)"
REQUEST_DELAY_SEC = 1.25
MAX_QUERIES = 18
PER_QUERY_LIMIT = 8

# Dual-track oriented queries (subset of seeds + screen vocabulary)
PRIORITY_QUERY_TERMS = (
    "calendly",
    "bookly",
    "lovable",
    "supabase",
    "vercel",
    "wordpress booking",
    "embed booking",
    "online booking",
    "half built",
    "production deploy",
    "bolt.new",
    "migration docker",
)

FIVERR_PROBE_URLS = (
    "https://www.fiverr.com/buyer_requests",
    "https://www.fiverr.com/search/gigs?query=calendly%20embed",
)

CLOSED_FREELANCER = frozenset({"frozen", "closed", "completed", "cancelled", "canceled", "awarded"})


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def job_search_keywords() -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    if SEEDS_PATH.exists():
        seeds = json.loads(SEEDS_PATH.read_text(encoding="utf-8"))
        for entry in seeds.get("keywords", []):
            track = entry.get("track") or ""
            if track not in ("预约工具接入", "AI 上线加固", "建站加预约"):
                continue
            kw = (entry.get("keyword") or "").strip()
            if len(kw) < 4:
                continue
            low = kw.lower()
            if low in seen:
                continue
            seen.add(low)
            queries.append(kw)
    for term in PRIORITY_QUERY_TERMS:
        low = term.lower()
        if low not in seen:
            seen.add(low)
            queries.append(term)
    return queries[:MAX_QUERIES]


def _budget_label(project: dict[str, Any]) -> str:
    cur = project.get("currency") or {}
    sign = cur.get("sign") or "$"
    budget = project.get("budget") or {}
    mn, mx = budget.get("minimum"), budget.get("maximum")
    if project.get("type") == "hourly" and mn is not None and mx is not None:
        return f"{sign}{mn}-{mx}/hr"
    if mn is not None and mx is not None:
        return f"{sign}{mn}-{mx}"
    if mn is not None:
        return f"{sign}{mn}"
    return ""


def _freelancer_status_label(raw: str) -> str:
    low = raw.lower()
    if low == "active":
        return "Open"
    if low in CLOSED_FREELANCER:
        return raw.capitalize()
    return raw or "unknown"


def _project_to_raw(project: dict[str, Any], query: str) -> dict[str, Any]:
    pid = project.get("id")
    seo = project.get("seo_url") or str(pid)
    url = f"https://www.freelancer.com/projects/{seo}"
    desc = project.get("description") or project.get("preview_description") or ""
    status_raw = str(project.get("status") or "unknown")
    jobs = project.get("jobs")
    skills = ""
    if isinstance(jobs, list):
        skills = ", ".join(str(j.get("name", j)) if isinstance(j, dict) else str(j) for j in jobs)
    return {
        "id": f"fl-{pid}",
        "platform": "freelancer",
        "title": project.get("title") or "",
        "description": desc,
        "skills": skills,
        "budget": _budget_label(project),
        "budget_raw": _budget_label(project),
        "status": _freelancer_status_label(status_raw),
        "url": url,
        "search_keyword": query,
        "fetched_at": hk_now_iso(),
        "_freelancer_status_raw": status_raw,
    }


def fetch_freelancer_projects(session: requests.Session, queries: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {"queries": len(queries), "fetched_projects": 0, "errors": []}
    by_id: dict[str, dict[str, Any]] = {}
    for i, query in enumerate(queries):
        if i > 0:
            time.sleep(REQUEST_DELAY_SEC)
        try:
            resp = session.get(
                FREELANCER_API,
                params={"query": query, "limit": PER_QUERY_LIMIT},
                timeout=45,
            )
            if resp.status_code == 429:
                meta["errors"].append(f"rate limited on query={query!r}")
                time.sleep(5)
                continue
            resp.raise_for_status()
            payload = resp.json()
            projects = (payload.get("result") or {}).get("projects") or []
            for p in projects:
                if p.get("deleted") or p.get("nonpublic"):
                    continue
                raw_status = str(p.get("status") or "").lower()
                if raw_status in CLOSED_FREELANCER:
                    continue
                rid = str(p.get("id"))
                if rid in by_id:
                    continue
                by_id[rid] = _project_to_raw(p, query)
            meta["fetched_projects"] = len(by_id)
        except requests.RequestException as exc:
            meta["errors"].append(f"{query!r}: {exc}")
    return list(by_id.values()), meta


def probe_fiverr(session: requests.Session) -> dict[str, Any]:
    """Public Fiverr pages only; never store cookies or bypass walls."""
    result: dict[str, Any] = {"attempted": True, "jobs": [], "skipped": False, "reason": None}
    for url in FIVERR_PROBE_URLS:
        try:
            resp = session.get(
                url,
                timeout=30,
                headers={"Accept": "text/html,application/json"},
                allow_redirects=True,
            )
            if resp.status_code in (401, 403):
                result["skipped"] = True
                result["reason"] = f"HTTP {resp.status_code} login/bot wall at {url}"
                return result
            text = (resp.text or "")[:8000].lower()
            if "sign in" in text and "buyer" in text and len(text) < 5000:
                result["skipped"] = True
                result["reason"] = f"login wall detected at {url}"
                return result
        except requests.RequestException as exc:
            result["skipped"] = True
            result["reason"] = str(exc)
            return result
    result["skipped"] = True
    result["reason"] = "no parseable public buyer-request feed (HTML only / blocked)"
    return result


def screened_to_job_record(raw: dict[str, Any], screened: Any) -> dict[str, Any]:
    rec = asdict(screened)
    rec["id"] = raw.get("id") or rec.get("id")
    rec["fetched_at"] = raw.get("fetched_at") or hk_now_iso()
    rec["budget_raw"] = rec.get("budget_raw") or raw.get("budget_raw") or raw.get("budget") or ""
    # asdict may expose pass_ on nested — gates already use "pass"
    if "pass_" in rec:
        del rec["pass_"]
    return rec


def run(merge_opportunities: bool = False) -> int:
    run_id = start_run("ingest_job_leads", {})
    try:
        session = _session()
        queries = job_search_keywords()
        raw_jobs, fl_meta = fetch_freelancer_projects(session, queries)
        time.sleep(REQUEST_DELAY_SEC)
        fv_meta = probe_fiverr(session)

        raw_by_id = {j["id"]: j for j in raw_jobs}
        screened = sort_results([screen_job(j) for j in raw_jobs])
        jobs = [
            screened_to_job_record(raw_by_id[r.id], r)
            for r in screened
            if r.id in raw_by_id
        ]

        source_note = (
            "Freelancer public API search; Fiverr public only; no login; no bid. "
            + (fv_meta.get("reason") or "Fiverr skipped")
            if fv_meta.get("skipped")
            else "Freelancer public API; Fiverr public probe"
        )

        out = {
            "updated_at": hk_now_iso(),
            "run_id": run_id,
            "source_note": source_note,
            "ingest": {
                "freelancer": fl_meta,
                "fiverr": fv_meta,
            },
            "jobs": jobs,
        }
        JOB_LEADS_PATH.parent.mkdir(parents=True, exist_ok=True)
        JOB_LEADS_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
        (PUBLIC_DATA_DIR / "job_leads.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        merged = 0
        if merge_opportunities and jobs:
            merged = merge_recommended_into_opportunities()

        finish_run(
            run_id,
            "success",
            counts={
                "jobs": len(jobs),
                "recommend": sum(1 for j in jobs if j.get("recommend")),
                "freelancer_raw": len(raw_jobs),
                "opportunity_merged": merged,
            },
            meta={"fiverr_skipped": fv_meta.get("skipped"), "fiverr_reason": fv_meta.get("reason")},
        )
        print(
            f"job_leads: {len(jobs)} jobs, "
            f"{sum(1 for j in jobs if j.get('recommend'))} recommend, "
            f"Fiverr skipped={fv_meta.get('skipped')}",
            flush=True,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        finish_run(run_id, "failed", error=str(exc))
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Freelancer/Fiverr open job leads")
    parser.add_argument("--no-merge-opportunities", action="store_true", help="Do not append job cards to opportunities.json")
    args = parser.parse_args()
    sys.exit(run(merge_opportunities=not args.no_merge_opportunities))


if __name__ == "__main__":
    main()
