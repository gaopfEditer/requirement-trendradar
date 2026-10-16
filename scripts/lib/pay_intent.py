from __future__ import annotations

TOOL_WORDS = ("tool", "software", "app", "integration", "api", "automation")
MONEY_WORDS = (
    "pricing",
    "cost",
    "freelance",
    "hire",
    "agency",
    "zapier",
    "make.com",
)
QUESTION_WORDS = ("how to", "best", " vs ", "alternative")


def pay_intent_score(keyword: str, related_queries: list[str]) -> int:
    """Heuristic 0–3, marked 【估】 in UI."""
    blob = " ".join([keyword.lower()] + [q.lower() for q in related_queries])
    score = 0
    if any(w in blob for w in TOOL_WORDS):
        score += 1
    if any(w in blob for w in MONEY_WORDS):
        score += 1
    if any(w in blob for w in QUESTION_WORDS):
        score += 1
    return min(score, 3)
