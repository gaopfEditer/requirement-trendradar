"""Freelancer job-search keywords from config/seeds.json (+ priority terms)."""
from __future__ import annotations

import json
from typing import Any

from scripts.lib.paths import CONFIG_DIR, DATA_DIR, PUBLIC_DATA_DIR, hk_now_iso

SEEDS_PATH = CONFIG_DIR / "seeds.json"
JOB_SEARCH_KEYWORDS_PATH = DATA_DIR / "job_search_keywords.json"
PUBLIC_JOB_SEARCH_KEYWORDS_PATH = PUBLIC_DATA_DIR / "job_search_keywords.json"

# Tracks included in ingest_job_leads Freelancer query= rotation
JOB_SEARCH_TRACKS: tuple[str, ...] = (
    "建站加预约",
    "预约工具接入",
    "AI 上线加固",
    "AI 客服",
    "AI Agent",
    "代码修复优化",
    "复杂集成",
)

MAX_QUERIES = 42
# Round-robin: each pass takes one keyword per track (in JOB_SEARCH_TRACKS order) until MAX_QUERIES.

PRIORITY_QUERY_TERMS: tuple[str, ...] = (
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
    "playwright agent",
    "whatsapp chatbot",
    "chrome extension mv3",
    "code review security",
    "appointment deposit stripe",
    "n8n ai agent",
    "stripe webhook debug",
)


def _load_seeds() -> dict[str, Any]:
    if not SEEDS_PATH.exists():
        return {}
    return json.loads(SEEDS_PATH.read_text(encoding="utf-8"))


def keywords_by_track(seeds: dict[str, Any] | None = None) -> dict[str, list[dict[str, str]]]:
    """Group seed entries by track; each item has keyword + heat (default hot)."""
    seeds = seeds if seeds is not None else _load_seeds()
    by_track: dict[str, list[dict[str, str]]] = {t: [] for t in JOB_SEARCH_TRACKS}
    seen_per_track: dict[str, set[str]] = {t: set() for t in JOB_SEARCH_TRACKS}
    for entry in seeds.get("keywords", []):
        track = entry.get("track") or ""
        if track not in by_track:
            continue
        kw = (entry.get("keyword") or "").strip()
        if len(kw) < 4:
            continue
        low = kw.lower()
        if low in seen_per_track[track]:
            continue
        seen_per_track[track].add(low)
        heat = (entry.get("heat") or "hot").strip().lower()
        if heat not in ("hot", "cold"):
            heat = "hot"
        by_track[track].append({"keyword": kw, "heat": heat})
    return by_track


def round_robin_select(
    by_track: dict[str, list[dict[str, str]]],
    max_queries: int,
    extra_terms: tuple[str, ...] = (),
) -> list[str]:
    """
    Fair coverage: round-robin one keyword per track per lap, then append priority terms.
    Stops at max_queries (default MAX_QUERIES).
    """
    queries: list[str] = []
    seen: set[str] = set()
    tracks = [t for t in JOB_SEARCH_TRACKS if by_track.get(t)]
    if not tracks:
        tracks = list(JOB_SEARCH_TRACKS)

    indices = {t: 0 for t in tracks}
    while len(queries) < max_queries:
        progressed = False
        for track in tracks:
            items = by_track.get(track) or []
            idx = indices[track]
            if idx >= len(items):
                continue
            kw = items[idx]["keyword"]
            indices[track] = idx + 1
            low = kw.lower()
            if low in seen:
                continue
            seen.add(low)
            queries.append(kw)
            progressed = True
            if len(queries) >= max_queries:
                break
        if not progressed:
            break

    for term in extra_terms:
        if len(queries) >= max_queries:
            break
        low = term.lower()
        if low not in seen and len(term.strip()) >= 2:
            seen.add(low)
            queries.append(term.strip())
    return queries[:max_queries]


def job_search_keywords(max_queries: int = MAX_QUERIES) -> list[str]:
    by_track = keywords_by_track()
    return round_robin_select(by_track, max_queries, PRIORITY_QUERY_TERMS)


def build_keyword_bank_document(seeds: dict[str, Any] | None = None) -> dict[str, Any]:
    by_track = keywords_by_track(seeds)
    tracks_out: list[dict[str, Any]] = []
    for track in JOB_SEARCH_TRACKS:
        kws = by_track.get(track) or []
        if not kws:
            continue
        tracks_out.append({"track": track, "keywords": kws})

    priority_rows = [{"keyword": t, "heat": "hot"} for t in PRIORITY_QUERY_TERMS]
    if priority_rows:
        tracks_out.append({"track": "优先级补充", "keywords": priority_rows})

    return {
        "updated_at": hk_now_iso(),
        "tracks": tracks_out,
    }


def publish_keyword_bank(seeds: dict[str, Any] | None = None) -> dict[str, Any]:
    doc = build_keyword_bank_document(seeds)
    payload = json.dumps(doc, ensure_ascii=False, indent=2)
    JOB_SEARCH_KEYWORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    JOB_SEARCH_KEYWORDS_PATH.write_text(payload, encoding="utf-8")
    PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_JOB_SEARCH_KEYWORDS_PATH.write_text(payload, encoding="utf-8")
    return doc
