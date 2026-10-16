from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from scripts.lib.paths import DATA_DIR, hk_now_iso

RUNS_PATH = DATA_DIR / "runs.json"


def _load() -> dict[str, Any]:
    if RUNS_PATH.exists():
        return json.loads(RUNS_PATH.read_text(encoding="utf-8"))
    return {"runs": []}


def _save(data: dict[str, Any]) -> None:
    RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def start_run(step: str, meta: dict[str, Any] | None = None) -> str:
    run_id = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    entry = {
        "run_id": run_id,
        "step": step,
        "status": "running",
        "started_at": hk_now_iso(),
        "ended_at": None,
        "counts": {},
        "error": None,
        "meta": meta or {},
    }
    data = _load()
    data["runs"].insert(0, entry)
    data["last_updated"] = hk_now_iso()
    _save(data)
    return run_id


def finish_run(
    run_id: str,
    status: str,
    counts: dict[str, Any] | None = None,
    error: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    data = _load()
    for entry in data["runs"]:
        if entry["run_id"] == run_id:
            entry["status"] = status
            entry["ended_at"] = hk_now_iso()
            if counts is not None:
                entry["counts"] = counts
            if error is not None:
                entry["error"] = error
            if meta:
                entry["meta"] = {**entry.get("meta", {}), **meta}
            break
    data["last_updated"] = hk_now_iso()
    _save(data)


def get_run(run_id: str) -> dict[str, Any] | None:
    for entry in _load()["runs"]:
        if entry["run_id"] == run_id:
            return entry
    return None
