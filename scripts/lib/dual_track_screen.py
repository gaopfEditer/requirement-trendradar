#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双轨接单筛选器（Freelancer / Upwork 通用）

对齐：/workspace/ops-master/出海接单操作细则-双轨流程-2026-10-17.md §1 / §4

逻辑（2026-10-17 重写）：
1) 关键词圈范围 — 工具点名词优先（嵌入/加固）；泛职称词降权或排除
2) 描述三关 — 预算 / 清晰交付 / 一期 1–3 天可验
3) 否决项 — 只要想法、整盘克隆、代管资金、站外骗全款、无限范围

输入：JSON / JSONL / CSV（字段见 --help）
输出：JSON（stdout 或 -o）；仍 Open 的帖排在前面

不爬登录墙、不自动投标。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# ---------------------------------------------------------------------------
# 词表：点名工具 = 高权；泛职称 = 降权/排除
# ---------------------------------------------------------------------------

# Freelancer 投标数：超过则不再「推荐投」（仍保留在列表供人工查看）
BID_COUNT_RECOMMEND_MAX = 99

EMBED_TOOLS = [
    "whatsapp business",
    "beds24",
    "calendly",
    "bookly",
    "amelia",
    "square appointments",
    "square online",
    "opentable",
    "resy",
    "acuity",
    "setmore",
    "simplybook",
    "appointlet",
    "youcanbook",
    "tidycal",
    "cal.com",
    "calcom",
]

EMBED_PHRASES = [
    "online booking",
    "add booking",
    "booking embed",
    "embed booking",
    "appointment booking",
    "reservation form",
    "reservation integration",
    "book now",
    "scheduling widget",
    "booking calendar",
    "wordpress booking",
    "booking plugin",
]

HARDEN_TOOLS = [
    "lovable",
    "loveable",  # common misspelling
    "lovalble",
    "bolt.new",
    "bolt new",
    "supabase",
    "vercel",
    "replit",
    "cursor",
    "v0.dev",
    "v0 ",
    "playwright",
    "n8n",
    "langchain",
    "openai api",
    "manifest v3",
    "ollama",
    "open webui",
    "litellm",
    "pgvector",
]

HARDEN_PHRASES = [
    "half built",
    "half-built",
    "production ready",
    "productionize",
    "harden",
    "health check",
    "deploy",
    "migration",
    "migrate",
    "self-hosted",
    "self hosted",
    "fix and deploy",
    "mvp launch",
    "ai mvp",
    "vibe code",
    "vibe coding",
    "chatbot",
    "ai agent",
    "chrome extension",
    "bug fix",
    "memory leak",
    "webhook",
    "owasp",
    "rate limit",
    "mcp server",
    "self hosted ai",
]

# 泛泛职称/海投词：出现且无工具点名 → 降权；仅有这些 → 排除
# 预约/日历领域语境（仅命中 EMBED_PHRASES 时需至少一条，避免搜索词污染）
BOOKING_DOMAIN = re.compile(
    r"\b("
    r"appointment|reservation|schedul(?:e|ing)|calendar|booking\s+(?:system|engine|plugin|widget|page|form)|"
    r"online\s+book|embed|widget|wordpress|woocommerce|salon|clinic|hotel|property|"
    r"ota|channel\s+manager|availability|time\s*slot|"
    r"beds24|calendly|bookly|acuity|setmore|simplybook|tidycal|square\s+appointments"
    r")\b",
    re.I,
)

# 与嵌入/预约交付无关的品类：无点名预约工具时排除
UNRELATED_CATEGORY = re.compile(
    r"\b("
    r"lead\s+gen(?:eration)?|appointment\s+setting|cold\s+call|outreach|"
    r"instagram\s+(?:outreach|marketing|growth)|seo\b|search\s+engine\s+optim|"
    r"rental\s+boyfriend|boyfriend\s+rental|dating\s+app|life\s+coach|"
    r"social\s+media\s+marketing|influencer|onlyfans|"
    r"virtual\s+assistant\s+for\s+lead"
    r")\b",
    re.I,
)

GENERIC_DEMOTE = [
    "website developer",
    "web developer",
    "full stack",
    "fullstack",
    "full-stack",
    "frontend developer",
    "backend developer",
    "software engineer",
    "hire a developer",
    "need a developer",
    "looking for developer",
    "wordpress developer",
    "react developer",
    "build me a website",
    "build a website",
    "create a website",
    "make a website",
]

# 否决：想法/克隆/资金/站外全款/无限范围
VETO_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("只要想法", re.compile(
        r"\b(just\s+(an?\s+)?idea|need\s+(an?\s+)?idea|brainstorm\s+only|"
        r"concept\s+only|no\s+budget\s+yet|looking\s+for\s+partner\s+to\s+build)\b",
        re.I,
    )),
    ("整盘克隆", re.compile(
        r"\b(clone\s+(of\s+)?(uber|airbnb|amazon|netflix|tiktok|instagram|whatsapp)|"
        r"like\s+(uber|airbnb|amazon|netflix)|"
        r"build\s+(me\s+)?(an?\s+)?(uber|airbnb)\s*(app|clone)?|"
        r"下一个\s*(uber|airbnb)|整盘克隆)\b",
        re.I,
    )),
    ("代管资金", re.compile(
        r"\b(hold\s+funds|hold\s+money|escrow\s+for\s+me|manage\s+(client\s+)?funds|"
        r"receive\s+payments\s+on\s+my\s+behalf|crypto\s+wallet\s+(access|seed)|"
        r"private\s+key|seed\s+phrase|代管资金|代收(款|钱))\b",
        re.I,
    )),
    ("站外骗全款", re.compile(
        r"\b(pay\s+(full|100%|everything)\s+(outside|off[- ]platform|via\s+(paypal|wire|crypto)\s+first)|"
        r"full\s+payment\s+(before|upfront)\s+(we\s+)?(start|chat)|"
        r"don'?t\s+use\s+(the\s+)?(platform|escrow)|"
        r"bypass\s+(the\s+)?(platform|escrow)|站外.*(全款|先付))\b",
        re.I,
    )),
    ("无限范围", re.compile(
        r"\b(unlimited\s+(revisions?|scope|features?)|open[- ]ended|"
        r"as\s+many\s+features?\s+as\s+needed|"
        r"build\s+everything|全功能|功能不限|无限(改|范围))\b",
        re.I,
    )),
    ("只要设计/全职", re.compile(
        r"\b(design\s+only|only\s+(need\s+)?(figma|mockups?)|"
        r"full[- ]time\s+(only|role|position)|long[- ]term\s+full[- ]time|"
        r"只要设计稿)\b",
        re.I,
    )),
]

BUDGET_NUM = re.compile(
    r"(?:"
    r"(?:USD|US\$|\$|CAD|A\$|AU\$|€|EUR|£|GBP|₹|INR|¥|CNY)\s*[\d,]+(?:\.\d+)?(?:\s*[-–—to]+\s*(?:USD|US\$|\$|CAD|A\$|AU\$|€|EUR|£|GBP|₹|INR)?\s*[\d,]+(?:\.\d+)?)?"
    r"|"
    r"[\d,]{2,}(?:\.\d+)?\s*(?:USD|CAD|AUD|EUR|GBP|INR)\b"
    r"|"
    r"\$\s*[\d,]+(?:\.\d+)?(?:\s*/\s*h(?:our)?|\s*[-–—to]+\s*\$?\s*[\d,]+)?"
    r")",
    re.I,
)

HOURLY_OK = re.compile(r"\b(hourly|per\s*hour|/h(?:r|our)?\b|时薪)\b", re.I)
NEGOTIABLE = re.compile(r"\b(negotiable|open\s+to\s+offers?|budget\s+flexible|可谈|面议)\b", re.I)

# 一期可切信号
PHASE1_OK = re.compile(
    r"\b("
    r"embed|integrat(?:e|ion)|plugin|widget|calendly|bookly|square|"
    r"deploy|vercel|docker|migrate|migration|fix|debug|harden|"
    r"stripe|auth|oauth|env(?:ironment)?|health\s*check|"
    r"phase\s*1|mvp|small\s+task|quick\s+(fix|job)|"
    r"add\s+(a\s+)?(form|button|page|booking)|"
    r"一期|嵌入|加固|上线"
    r")\b",
    re.I,
)

PHASE1_BAD = re.compile(
    r"\b("
    r"from\s+scratch\s+(saas|marketplace|platform)|"
    r"complete\s+(saas|marketplace|platform)\s+with\s+\d{2,}\s+screens?|"
    r"20\+?\s*screens?|full\s+product\s+build|"
    r"整站从零|从零(做|开发).*平台"
    r")\b",
    re.I,
)

CLEAR_DELIVERABLE = re.compile(
    r"\b("
    r"embed|integrat|deploy|migrat|fix|add\s+\w+|setup|install|"
    r"connect\s+\w+|stripe|supabase|wordpress|netlify|"
    r"reservation|booking\s+(form|page|widget|system)|"
    r"production|launch|audit"
    r")\b",
    re.I,
)

OPEN_STATUSES = {
    "open",
    "open for bidding",
    "active",
    "published",
    "accepting proposals",
    "hiring",
}
CLOSED_STATUSES = {
    "closed",
    "completed",
    "cancelled",
    "canceled",
    "in progress",
    "awarded",
    "hired",
    "filled",
}


@dataclass
class GateResult:
    name: str
    pass_: bool
    reason: str


@dataclass
class ScreenResult:
    id: str
    title: str
    url: str
    platform: str
    status: str
    is_open: bool
    track: str  # 嵌入 / 加固 / 未知 / 排除
    keyword_tier: str  # tool / phrase / generic_demote / generic_exclude / none
    keyword_hits: list[str] = field(default_factory=list)
    gates: list[dict[str, Any]] = field(default_factory=list)
    all_gates_pass: bool = False
    veto: Optional[str] = None
    recommend: bool = False
    recommend_note: str = ""
    budget_raw: str = ""
    score: float = 0.0


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _content_blob(job: dict[str, Any]) -> str:
    """Title/description/skills only — 不用 search_keyword，避免检索词假命中。"""
    parts = [
        str(job.get("title") or ""),
        str(job.get("description") or job.get("desc") or ""),
        str(job.get("skills") or ""),
    ]
    return _norm(" ".join(parts))


def _blob(job: dict[str, Any]) -> str:
    parts = [
        str(job.get("title") or ""),
        str(job.get("description") or job.get("desc") or ""),
        str(job.get("skills") or ""),
        str(job.get("search_keyword") or job.get("query") or ""),
    ]
    return _norm(" ".join(parts))


def _status_info(job: dict[str, Any]) -> tuple[str, bool]:
    raw = str(job.get("status") or job.get("state") or "unknown").strip()
    low = raw.lower()
    if low in OPEN_STATUSES or "open for bidding" in low or low == "open":
        return raw, True
    if low in CLOSED_STATUSES or any(c in low for c in ("closed", "complet", "cancel", "award", "progress", "hired")):
        return raw, False
    # unknown：不剔除，但不优先
    return raw, low in ("", "unknown")


def classify_keywords(text: str) -> tuple[str, str, list[str]]:
    """Return (track, tier, hits). track: 嵌入/加固/未知/排除"""
    hits: list[str] = []
    embed_tool_score = 0
    embed_phrase_score = 0
    harden_tool_score = 0
    harden_phrase_score = 0

    for t in EMBED_TOOLS:
        if t in text:
            hits.append(t)
            embed_tool_score += 3
    for p in EMBED_PHRASES:
        if p in text:
            hits.append(p)
            embed_phrase_score += 2

    for t in HARDEN_TOOLS:
        if t in text:
            hits.append(t)
            harden_tool_score += 3
    for p in HARDEN_PHRASES:
        if p in text:
            hits.append(p)
            harden_phrase_score += 2

    embed_score = embed_tool_score + embed_phrase_score
    harden_score = harden_tool_score + harden_phrase_score
    named_booking_tool = embed_tool_score >= 3

    generic_hits = [g for g in GENERIC_DEMOTE if g in text]
    has_tool = embed_tool_score >= 3 or harden_tool_score >= 3
    has_phrase = (embed_phrase_score >= 2 or harden_phrase_score >= 2) and not has_tool

    if embed_score == 0 and harden_score == 0:
        if generic_hits:
            return "排除", "generic_exclude", generic_hits
        return "未知", "none", []

    if UNRELATED_CATEGORY.search(text) and not named_booking_tool:
        return "排除", "generic_exclude", hits + ["unrelated_category"]

    if embed_phrase_score > 0 and embed_tool_score == 0 and not BOOKING_DOMAIN.search(text):
        return "排除", "generic_exclude", hits + ["booking_context_missing"]

    if embed_score >= harden_score:
        track = "嵌入"
    else:
        track = "加固"
    # 双轨交界：两边都够工具分
    if embed_tool_score >= 3 and harden_tool_score >= 3:
        track = "加固" if harden_score > embed_score else "嵌入"
        if abs(embed_score - harden_score) <= 1:
            track = "加固+嵌入"

    if has_tool:
        tier = "tool"
    elif has_phrase or embed_phrase_score >= 2 or harden_phrase_score >= 2:
        tier = "phrase"
    else:
        tier = "none"

    if generic_hits and not has_tool:
        tier = "generic_demote"
        hits = hits + generic_hits

    # 去重保序
    seen = set()
    uniq = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            uniq.append(h)
    return track, tier, uniq


def check_veto(text: str) -> Optional[str]:
    for label, pat in VETO_PATTERNS:
        if pat.search(text):
            return label
    return None


def gate_budget(job: dict[str, Any], text: str) -> GateResult:
    budget_fields = " ".join(
        str(job.get(k) or "")
        for k in ("budget", "budget_min", "budget_max", "price", "salary", "budget_raw")
    )
    combined = f"{budget_fields} {text}"
    if BUDGET_NUM.search(combined):
        return GateResult("预算", True, "有明确数字或区间")
    if HOURLY_OK.search(combined) and NEGOTIABLE.search(combined):
        return GateResult("预算", True, "时薪且可谈")
    if HOURLY_OK.search(combined):
        return GateResult("预算", True, "标明时薪（需人工确认底线）")
    if NEGOTIABLE.search(combined):
        return GateResult("预算", True, "标明可谈/面议（偏弱，建议人工看）")
    return GateResult("预算", False, "无预算")


def gate_clarity(text: str, tier: str) -> GateResult:
    if CLEAR_DELIVERABLE.search(text) or tier in ("tool", "phrase"):
        # 点名工具额外加分语义
        if tier == "tool":
            return GateResult("清晰", True, "点名工具/可一句话说清交付")
        return GateResult("清晰", True, "描述含可执行交付动词")
    # 极短糊需求
    if len(text) < 40:
        return GateResult("清晰", False, "需求糊（过短）")
    return GateResult("清晰", False, "需求糊（说不清交付物）")


def gate_phase1(text: str) -> GateResult:
    if PHASE1_BAD.search(text) and not PHASE1_OK.search(text):
        return GateResult("一期", False, "要整盘自研/大屏从零")
    if PHASE1_OK.search(text):
        return GateResult("一期", True, "可切 1–3 天可验收一期")
    # 有 booking+embed 类已在 PHASE1_OK；否则保守不过
    if re.search(r"\b(clone|marketplace|social\s+media\s+saas|full\s+saas)\b", text, re.I):
        return GateResult("一期", False, "无限范围/整盘产品倾向")
    return GateResult("一期", False, "看不出可切的一期")


def _bid_count(job: dict[str, Any]) -> int | None:
    for key in ("bid_count", "proposals_count"):
        raw = job.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def gate_competition(bid_count: int | None) -> GateResult:
    if bid_count is None:
        return GateResult("竞争", True, "无公开投标数")
    if bid_count >= BID_COUNT_RECOMMEND_MAX:
        return GateResult("竞争", False, f"投标过多（{bid_count}≥{BID_COUNT_RECOMMEND_MAX + 1}）")
    if bid_count >= 75:
        return GateResult("竞争", True, f"投标偏多（{bid_count}），谨慎")
    return GateResult("竞争", True, f"投标数 {bid_count}")


def score_result(r: ScreenResult) -> float:
    s = 0.0
    if r.is_open:
        s += 50
    if r.recommend:
        s += 30
    if r.keyword_tier == "tool":
        s += 20
    elif r.keyword_tier == "phrase":
        s += 12
    elif r.keyword_tier == "generic_demote":
        s -= 10
    elif r.keyword_tier == "generic_exclude":
        s -= 40
    if r.all_gates_pass:
        s += 15
    if r.veto:
        s -= 100
    if r.track in ("嵌入", "加固", "加固+嵌入"):
        s += 5
    return s


def screen_job(job: dict[str, Any]) -> ScreenResult:
    jid = str(job.get("id") or job.get("url") or job.get("title") or "unknown")
    title = str(job.get("title") or "")
    url = str(job.get("url") or "")
    platform = str(job.get("platform") or job.get("source") or "unknown")
    status, is_open = _status_info(job)
    text = _blob(job)
    content_text = _content_blob(job)
    budget_raw = str(
        job.get("budget")
        or job.get("budget_raw")
        or " ".join(
            str(job.get(k) or "")
            for k in ("budget_min", "budget_max")
            if job.get(k) is not None
        )
    )

    track, tier, hits = classify_keywords(content_text)
    veto = check_veto(text)
    bid_n = _bid_count(job)

    gates: list[GateResult] = []
    if track == "排除" or tier == "generic_exclude":
        # 关键词关未过：仍跑三关供审计，但不推荐
        gates.append(GateResult("关键词", False, "仅有泛职称词，已排除"))
    elif tier == "generic_demote":
        gates.append(GateResult("关键词", True, "有双轨词但含泛词，已降权"))
    elif tier in ("tool", "phrase"):
        gates.append(GateResult("关键词", True, f"命中{tier}: {', '.join(hits[:6])}"))
    else:
        gates.append(GateResult("关键词", False, "未命中嵌入/加固词"))

    gates.append(gate_budget(job, text))
    gates.append(gate_clarity(content_text, tier))
    gates.append(gate_phase1(content_text))
    gates.append(gate_competition(bid_n))

    # 关键词排除视作未过关
    content_gates = [g for g in gates if g.name != "关键词"]
    keyword_ok = gates[0].pass_
    all_pass = keyword_ok and all(g.pass_ for g in content_gates) and not veto

    recommend = bool(all_pass and is_open and track != "排除")
    note = ""
    if veto:
        note = f"否决：{veto}"
    elif not is_open:
        note = "非 Open，仅作样例"
    elif not keyword_ok:
        note = "关键词未过"
    elif not all(g.pass_ for g in content_gates):
        failed = [g for g in content_gates if not g.pass_]
        note = "三关未过：" + "; ".join(f"{g.name}:{g.reason}" for g in failed)
    elif recommend:
        note = "推荐投"

    # 低预算人工标谨慎：INR 且上限很低等 — 软提示不否决
    if recommend and re.search(r"(₹|INR).{0,20}(1[05]00|600|250)\b", budget_raw + " " + text, re.I):
        note = "推荐但预算极低，谨慎"
    if recommend and re.search(r"\$\s*([1-9]|[1-4]\d)(\.\d+)?\s*$", budget_raw.strip()):
        note = "推荐但预算偏低，谨慎"

    r = ScreenResult(
        id=jid,
        title=title,
        url=url,
        platform=platform,
        status=status,
        is_open=is_open,
        track=track if track != "排除" else "排除",
        keyword_tier=tier,
        keyword_hits=hits,
        gates=[{"name": g.name, "pass": g.pass_, "reason": g.reason} for g in gates],
        all_gates_pass=all_pass,
        veto=veto,
        recommend=recommend,
        recommend_note=note,
        budget_raw=budget_raw,
    )
    r.score = score_result(r)
    return r


def load_jobs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        jobs = []
        for i, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            jobs.append(json.loads(line))
        return jobs
    if path.suffix.lower() == ".csv":
        rows = list(csv.DictReader(raw.splitlines()))
        return rows
    data = json.loads(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "jobs" in data:
        return list(data["jobs"])
    if isinstance(data, dict):
        return [data]
    raise ValueError("Unsupported JSON shape")


def sort_results(results: list[ScreenResult]) -> list[ScreenResult]:
    # Open 优先，再 recommend，再 score
    return sorted(
        results,
        key=lambda r: (
            0 if r.is_open else 1,
            0 if r.recommend else 1,
            -r.score,
            r.title.lower(),
        ),
    )


def to_markdown(results: list[ScreenResult]) -> str:
    lines = [
        "# 双轨筛选结果",
        "",
        f"- 生成：{datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M %Z')}",
        f"- 条数：{len(results)}；推荐：{sum(1 for r in results if r.recommend)}",
        "",
        "| Open | 推荐 | 轨 | 标题 | 预算 | 三关 | 否决/备注 | URL |",
        "|------|------|----|------|------|------|-----------|-----|",
    ]
    for r in results:
        gates_s = "; ".join(
            f"{g['name']}{'✓' if g['pass'] else '✗'}({g['reason']})" for g in r.gates
        )
        lines.append(
            f"| {'Y' if r.is_open else 'N'} | {'Y' if r.recommend else 'N'} | {r.track} | "
            f"{r.title[:60].replace('|', '/')} | {r.budget_raw[:24].replace('|', '/')} | "
            f"{gates_s.replace('|', '/')} | {(r.veto or r.recommend_note)[:40].replace('|', '/')} | {r.url} |"
        )
    return "\n".join(lines) + "\n"


SAMPLE_JOBS = [
    {
        "id": "pos-1",
        "platform": "freelancer",
        "title": "POS System Migration to Local Server",
        "description": "Move PartFlow POS off Lovable Cloud to self-hosted Supabase and Docker. Need migration and deploy docs. Budget $250-750.",
        "budget": "$250-750",
        "status": "Open",
        "url": "https://www.freelancer.com/projects/docker/pos-system-migration-local-server",
    },
    {
        "id": "generic-1",
        "platform": "upwork",
        "title": "Need a Full Stack Website Developer",
        "description": "Looking for an experienced web developer to build me a website. Full stack preferred.",
        "budget": "",
        "status": "Open",
        "url": "https://example.com/generic",
    },
    {
        "id": "calendly-1",
        "platform": "freelancer",
        "title": "Add Calendly embed to WordPress site",
        "description": "Need someone to embed Calendly on our existing WordPress pages and style the book button. Fixed $150.",
        "budget": "$150",
        "status": "Open",
        "url": "https://example.com/calendly",
    },
    {
        "id": "clone-1",
        "platform": "freelancer",
        "title": "Build Uber clone app",
        "description": "Need a full Uber clone with unlimited features. Pay full outside platform first via crypto.",
        "budget": "$5000",
        "status": "Open",
        "url": "https://example.com/uber",
    },
    {
        "id": "closed-1",
        "platform": "freelancer",
        "title": "Lovable to Vercel deploy",
        "description": "Deploy half built lovable app to vercel with env and stripe. $200.",
        "budget": "$200",
        "status": "Closed",
        "url": "https://example.com/closed",
    },
]


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="双轨三关接单筛选（Freelancer/Upwork）")
    p.add_argument("-i", "--input", type=Path, help="jobs.json / .jsonl / .csv")
    p.add_argument("-o", "--output", type=Path, help="写出 JSON 结果")
    p.add_argument("--md", type=Path, help="同时写出 Markdown 表")
    p.add_argument("--sample", action="store_true", help="跑内置样例（无 -i 时默认）")
    p.add_argument("--recommend-only", action="store_true", help="只输出推荐帖")
    args = p.parse_args(argv)

    if args.input:
        jobs = load_jobs(args.input)
    else:
        jobs = SAMPLE_JOBS
        print("（未给 -i，使用内置样例）", file=sys.stderr)

    results = sort_results([screen_job(j) for j in jobs])
    if args.recommend_only:
        results = [r for r in results if r.recommend]

    payload = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "logic": "dual-track-v2026-10-17: keyword→3gates→veto; open first",
        "count": len(results),
        "recommend_count": sum(1 for r in results if r.recommend),
        "results": [asdict(r) for r in results],
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(text)

    if args.md:
        args.md.write_text(to_markdown(results), encoding="utf-8")
        print(f"Wrote {args.md}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
