from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = ROOT / "raw"
UPLOADS_DIR = ROOT / "uploads"
PUBLIC_DIR = ROOT / "public"
PUBLIC_DATA_DIR = PUBLIC_DIR / "data"
FIXTURES_DIR = ROOT / "fixtures"

for d in (DATA_DIR, RAW_DIR, UPLOADS_DIR, PUBLIC_DIR, PUBLIC_DATA_DIR):
    d.mkdir(parents=True, exist_ok=True)


def hk_now_iso() -> str:
    from datetime import datetime, timezone, timedelta

    hk = timezone(timedelta(hours=8))
    return datetime.now(hk).strftime("%Y-%m-%d %H:%M:%S %Z")
