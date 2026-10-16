from __future__ import annotations

from datetime import datetime, timezone, timedelta
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

HK = timezone(timedelta(hours=8))


def hk_now() -> datetime:
    return datetime.now(HK)


def hk_now_iso() -> str:
    return hk_now().strftime("%Y-%m-%d %H:%M:%S %Z")


def hk_now_iso8601() -> str:
    return hk_now().strftime("%Y-%m-%dT%H:%M:%S+08:00")


def to_iso8601_hk(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=HK)
    else:
        dt = dt.astimezone(HK)
    return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def parse_updated_at_to_iso(value: str | None) -> str | None:
    """Parse pipeline timestamps into ISO +08:00."""
    if not value:
        return None
    cleaned = value.strip().replace(" UTC+08:00", "").replace(" HKT", "").replace(" %Z", "")
    if "T" in cleaned:
        try:
            return to_iso8601_hk(datetime.fromisoformat(cleaned.replace("Z", "+00:00")))
        except ValueError:
            pass
    try:
        dt = datetime.strptime(cleaned[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=HK)
        return to_iso8601_hk(dt)
    except ValueError:
        return None


def format_hk_display(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(HK)
    except ValueError:
        return iso
    return dt.strftime("%Y-%m-%d %H:%M")


def iso_week_label(dt: datetime | None = None) -> str:
    d = (dt or hk_now()).astimezone(HK)
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"
