"""Map screened job leads into opportunity cards (optional merge)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from scripts.lib.paths import DATA_DIR, hk_now_iso

JOB_LEADS_PATH = DATA_DIR / "job_leads.json"
OPPORTUNITIES_PATH = DATA_DIR / "opportunities.json"

TRACK_EN = {
    "嵌入": "Embed booking",
    "加固": "AI harden",
    "加固+嵌入": "Embed + harden",
    "排除": "Excluded",
    "未知": "Unknown",
}

BOUNDARY = "不登录爬取、不自动投标、不存 cookie；外链仅作人工查阅。"
COST = "人工提案与沟通【估】；本站不代投。"
VERIFY = "打开外链核对 Open 与预算 → 用提案四件套投递 → 7 天内无回复则放弃。"


def _normalize_job_lead_core(jid: str) -> str:
    """Strip platform / card prefixes so IDs stay stable (no job-fl-fl-…)."""
    core = str(jid or "").strip()
    while True:
        for prefix in ("job-fl-", "job-fv-", "fl-", "fv-"):
            if core.startswith(prefix):
                core = core[len(prefix) :]
                break
        else:
            break
    return core


def opportunity_card_id(platform: str, jid: str) -> str:
    core = _normalize_job_lead_core(jid)
    prefix = "job-fl-" if platform == "freelancer" else "job-fv-"
    return f"{prefix}{core}"


def _is_job_lead_card_id(cid: str) -> bool:
    return str(cid or "").startswith(("job-fl-", "job-fv-"))


def _budget_usd_min(budget_raw: str) -> float | None:
    nums = re.findall(r"\$\s*([\d,]+(?:\.\d+)?)", budget_raw or "")
    if not nums:
        return None
    try:
        return min(float(n.replace(",", "")) for n in nums)
    except ValueError:
        return None


def job_to_opportunity_card(job: dict[str, Any]) -> dict[str, Any]:
    platform = job.get("platform") or "freelancer"
    jid = str(job.get("id") or "")
    cid = opportunity_card_id(platform, jid)

    track_cn = job.get("track") or "未知"
    track = TRACK_EN.get(track_cn, track_cn)
    tier = job.get("keyword_tier") or "none"
    pay = 2 if tier == "tool" else (1 if tier == "phrase" else 0)

    recommend = bool(job.get("recommend"))
    veto = job.get("veto")
    url = job.get("url") or ""
    title = job.get("title") or "Untitled job"

    if veto:
        verdict = "否"
    elif recommend and job.get("all_gates_pass") and (_budget_usd_min(job.get("budget_raw") or "") or 0) >= 100:
        verdict = "做"
    elif recommend:
        verdict = "观察"
    else:
        verdict = "否"

    action = f"针对「{title}」— {url} · 用提案四件套投，不代投。"

    hk = timezone(timedelta(hours=8))
    today = datetime.now(hk).strftime("%Y-%m-%d")

    return {
        "id": cid,
        "title": title,
        "track": track,
        "trends_hit": "no",
        "ranking_hit": "no",
        "pay_intent_score": pay if recommend else 0,
        "geo": "US",
        "slope_90d": None,
        "rank_delta": None,
        "ranking_ref": {
            "name": title,
            "url": url,
            "source": platform,
            "job_lead_id": jid,
        },
        "trends_ref": None,
        "skill_fit": "软件交付",
        "created_at": today,
        "updated_at": hk_now_iso(),
        "verdict": verdict,
        "action": action,
        "cost": COST,
        "boundary": BOUNDARY,
        "verify": VERIFY,
        "verdict_manual": False,
        "source": "job_lead",
    }


def merge_recommended_into_opportunities() -> int:
    """Append recommend==true job cards to opportunities.json; returns count added."""
    if not JOB_LEADS_PATH.exists() or not OPPORTUNITIES_PATH.exists():
        return 0
    leads_doc = json.loads(JOB_LEADS_PATH.read_text(encoding="utf-8"))
    opp_doc = json.loads(OPPORTUNITIES_PATH.read_text(encoding="utf-8"))
    cards: list[dict] = list(opp_doc.get("cards") or [])
    cards = [c for c in cards if not _is_job_lead_card_id(str(c.get("id", "")))]
    existing_ids = {c["id"] for c in cards}
    added = 0
    updated = 0
    for job in leads_doc.get("jobs") or []:
        if not job.get("recommend"):
            continue
        card = job_to_opportunity_card(job)
        if card["id"] in existing_ids:
            for i, old in enumerate(cards):
                if old.get("id") == card["id"]:
                    cards[i] = card
                    updated += 1
                    break
            continue
        cards.append(card)
        existing_ids.add(card["id"])
        added += 1
    verdict_order = {"做": 0, "观察": 1, "否": 2}
    cards.sort(key=lambda c: (verdict_order.get(c["verdict"], 9), -c.get("pay_intent_score", 0), c["title"]))
    opp_doc["cards"] = cards
    opp_doc["updated_at"] = hk_now_iso()
    OPPORTUNITIES_PATH.write_text(json.dumps(opp_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return added
