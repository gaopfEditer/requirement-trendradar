from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from scripts.lib.paths import RAW_DIR

DATE_RE = re.compile(r"_(\d{8})\.json$")


def prune_raw_older_than_days(days: int = 30) -> int:
    cutoff = datetime.utcnow().date() - timedelta(days=days)
    removed = 0
    for path in RAW_DIR.glob("*.json"):
        m = DATE_RE.search(path.name)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1), "%Y%m%d").date()
        except ValueError:
            continue
        if d < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed
