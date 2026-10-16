from __future__ import annotations

from typing import Literal

SlopeLabel = Literal["上升", "持平", "下降"]


def slope_from_series(values: list[int | float]) -> tuple[SlopeLabel, float]:
    """
    Estimate 90d slope from interest-over-time points (relative 0–100).
    Returns label and raw delta 【估】.
    """
    if len(values) < 4:
        return "持平", 0.0
    n = len(values)
    third = max(1, n // 3)
    early = values[:third]
    late = values[-third:]
    early_avg = sum(early) / len(early)
    late_avg = sum(late) / len(late)
    delta = late_avg - early_avg
    if delta > 5:
        return "上升", delta
    if delta < -5:
        return "下降", delta
    return "持平", delta
