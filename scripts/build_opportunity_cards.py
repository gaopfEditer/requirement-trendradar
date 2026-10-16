#!/usr/bin/env python3
"""C. build_opportunity_cards — cross Trends + rankings into opportunity cards."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone

from scripts.lib.paths import CONFIG_DIR, DATA_DIR, hk_now_iso
from scripts.lib.runs import finish_run, start_run

OPPORTUNITIES_PATH = DATA_DIR / "opportunities.json"
TRENDS_PATH = DATA_DIR / "trends_daily.json"
DELTA_PATH = DATA_DIR / "rankings_delta.json"
SEEDS_PATH = CONFIG_DIR / "seeds.json"

SKILL_KEYWORDS = {
    "软件交付": ("api", "integration", "app", "software", "automation", "bot", "template"),
    "信息整理": ("audit", "tracker", "notification", "alert", "docs"),
    "自动化": ("n8n", "make.com", "zapier", "workflow", "slack", "telegram"),
}


def slug_id(title: str) -> str:
    h = hashlib.sha256(title.encode("utf-8")).hexdigest()[:12]
    base = re.sub(r"[^a-z0-9]+", "-", title.lower())[:40].strip("-")
    return f"{base}-{h}" if base else h


def infer_skill_fit(title: str, tags: list[str]) -> str:
    blob = (title + " " + " ".join(tags)).lower()
    scores = {k: sum(1 for w in words if w in blob) for k, words in SKILL_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "落不上"
    return best


def default_verdict(trends_up: bool, ranking_up: bool, pay: int, has_rank: bool) -> str:
    if pay == 0 and not has_rank:
        return "否"
    if trends_up and ranking_up:
        return "观察"
    if trends_up:
        return "观察"
    if ranking_up:
        return "观察"
    return "观察"


def template_sections(title: str, track: str, trends_up: bool, ranking_up: bool, pay: int) -> dict[str, str]:
    action = f"针对「{title}」({track})：做 1 页英文落地页 + 可演示 MVP（或 Notion/视频样片），在 Upwork/Fiverr 或 PH 评论区验证需求。"
    if trends_up and ranking_up:
        action = f"双信号：{title} — 优先人工深读 PH 产品与 Trends 相关查询，48h 内出 1 条可投递案例研究。"
    cost = "估 4–12 小时调研 + 8–24 小时演示【估】；无付费 SEO/广告。"
    boundary = "不承诺订单；不自动发帖/投标；不爬付费榜；数字均为公开源启发式【估】。"
    verify = "① 找 3 个目标用户聊或冷邮 ② 投 1 个小单或固定价 gig ③ 记录回复率；7 天内无互动则降为「否」。"
    if pay >= 2:
        verify = "付费意图分较高【估】：优先看 pricing/hire 类相关查询，做报价单 A/B 测试 2 版。"
    return {"action": action, "cost": cost, "boundary": boundary, "verify": verify}


def load_existing() -> dict[str, dict]:
    if not OPPORTUNITIES_PATH.exists():
        return {}
    data = json.loads(OPPORTUNITIES_PATH.read_text(encoding="utf-8"))
    return {c["id"]: c for c in data.get("cards", [])}


def run(demo: bool = False) -> int:
    run_id = start_run("build_opportunity_cards", {})
    try:
        if not TRENDS_PATH.exists():
            raise FileNotFoundError("trends_daily.json missing — run ingest_trends first")
        trends_doc = json.loads(TRENDS_PATH.read_text(encoding="utf-8"))
        delta_items: list[dict] = []
        if DELTA_PATH.exists():
            delta_items = json.loads(DELTA_PATH.read_text(encoding="utf-8")).get("items", [])

        seeds = json.loads(SEEDS_PATH.read_text(encoding="utf-8"))
        default_geo = seeds.get("default_geo", "US")

        # Index trends: prefer default geo per keyword
        trends_by_kw: dict[str, dict] = {}
        for it in trends_doc.get("items", []):
            kw = it["keyword"]
            if kw not in trends_by_kw or it.get("geo") == default_geo:
                trends_by_kw[kw] = it

        ranking_hits: dict[str, dict] = {}
        for it in delta_items:
            name_l = (it.get("name") or "").lower()
            delta = it.get("rank_delta")
            is_up = it.get("rank_prev") is None or (delta is not None and delta < 0)
            if is_up or it.get("signal_note") == "新进榜":
                ranking_hits[name_l] = it

        existing = load_existing()
        hk = timezone(timedelta(hours=8))
        today = datetime.now(hk).strftime("%Y-%m-%d")
        cards: list[dict] = []
        seen_ids: set[str] = set()

        # From seeds / trends
        for entry in seeds.get("keywords", []):
            kw = entry["keyword"]
            track = entry.get("track", "未分类")
            tr = trends_by_kw.get(kw)
            trends_up = tr and tr.get("slope_90d") == "上升"
            pay = tr.get("pay_intent_score", 0) if tr else 0
            related_rank = None
            for name_l, rit in ranking_hits.items():
                if kw.split()[0].lower() in name_l or any(part.lower() in name_l for part in kw.split() if len(part) > 3):
                    related_rank = rit
                    break
            ranking_up = related_rank is not None
            title = kw
            cid = slug_id(f"{track}:{kw}")
            card = {
                "id": cid,
                "title": title,
                "track": track,
                "trends_hit": "yes" if trends_up else "no",
                "ranking_hit": "yes" if ranking_up else "no",
                "pay_intent_score": pay,
                "geo": tr.get("geo", default_geo) if tr else default_geo,
                "slope_90d": tr.get("slope_90d") if tr else None,
                "rank_delta": related_rank.get("rank_delta") if related_rank else None,
                "ranking_ref": related_rank,
                "trends_ref": tr,
                "skill_fit": infer_skill_fit(kw, tr.get("related_queries", []) if tr else []),
                "created_at": today,
                "updated_at": hk_now_iso(),
            }
            if cid in existing and existing[cid].get("verdict_manual"):
                prev = existing[cid]
                card["verdict"] = prev["verdict"]
                card["action"] = prev.get("action", "")
                card["cost"] = prev.get("cost", "")
                card["boundary"] = prev.get("boundary", "")
                card["verify"] = prev.get("verify", "")
                card["last_reviewed_at"] = prev.get("last_reviewed_at")
                card["reviewer"] = prev.get("reviewer")
                card["verdict_manual"] = True
            else:
                v = default_verdict(trends_up, ranking_up, pay, ranking_up)
                if card["skill_fit"] == "落不上":
                    v = "否"
                sections = template_sections(title, track, bool(trends_up), ranking_up, pay)
                card["verdict"] = v
                card.update(sections)
                card["verdict_manual"] = False
            cards.append(card)
            seen_ids.add(cid)

        # Ranking-only newcomers as cards
        for it in delta_items:
            if it.get("signal_note") not in ("新进榜",) and not (
                it.get("rank_delta") is not None and it["rank_delta"] < 0
            ):
                continue
            name = it.get("name") or ""
            if not name:
                continue
            title = name
            cid = slug_id(f"ph:{name}")
            if cid in seen_ids:
                continue
            track = (it.get("category_tags") or ["Product Hunt"])[0]
            card = {
                "id": cid,
                "title": title,
                "track": track,
                "trends_hit": "no",
                "ranking_hit": "yes",
                "pay_intent_score": 0,
                "geo": default_geo,
                "slope_90d": None,
                "rank_delta": it.get("rank_delta"),
                "ranking_ref": it,
                "trends_ref": None,
                "skill_fit": infer_skill_fit(name, it.get("category_tags", [])),
                "created_at": today,
                "updated_at": hk_now_iso(),
            }
            if cid in existing and existing[cid].get("verdict_manual"):
                prev = existing[cid]
                card.update({k: prev[k] for k in ("verdict", "action", "cost", "boundary", "verify", "last_reviewed_at", "reviewer") if k in prev})
                card["verdict_manual"] = True
            else:
                v = "观察" if card["skill_fit"] != "落不上" else "否"
                card["verdict"] = v
                card.update(template_sections(title, track, False, True, 0))
                card["verdict_manual"] = False
            cards.append(card)

        # Sort: 观察 first, then pay_intent desc
        verdict_order = {"做": 0, "观察": 1, "否": 2}
        cards.sort(key=lambda c: (verdict_order.get(c["verdict"], 9), -c.get("pay_intent_score", 0), c["title"]))

        out = {
            "updated_at": hk_now_iso(),
            "run_id": run_id,
            "cards": cards,
        }
        OPPORTUNITIES_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        finish_run(run_id, "success", counts={"cards": len(cards)})
        return 0
    except Exception as exc:  # noqa: BLE001
        finish_run(run_id, "failed", error=str(exc))
        return 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    sys.exit(run(demo=args.demo))


if __name__ == "__main__":
    main()
