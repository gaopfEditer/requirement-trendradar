#!/usr/bin/env python3
"""D. publish_site — copy JSON snapshots into public/data for static site."""
from __future__ import annotations

import argparse
import json
import shutil
import sys

from scripts.lib.meta_builder import build_meta, write_meta
from scripts.lib.paths import DATA_DIR, PUBLIC_DATA_DIR, hk_now_iso8601
from scripts.lib.runs import finish_run, start_run

FILES = (
    "opportunities.json",
    "trends_daily.json",
    "rankings_daily.json",
    "rankings_delta.json",
    "runs.json",
    "weekly_movers.json",
)


def run() -> int:
    run_id = start_run("publish_site", {})
    try:
        PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
        copied = 0
        for name in FILES:
            src = DATA_DIR / name
            if src.exists():
                shutil.copy2(src, PUBLIC_DATA_DIR / name)
                copied += 1
        finish_run(run_id, "success", counts={"files": copied})
        write_meta()
        shutil.copy2(DATA_DIR / "meta.json", PUBLIC_DATA_DIR / "meta.json")
        meta = build_meta()
        manifest = {
            "published_at": hk_now_iso8601(),
            "updated_at": meta.get("updated_at"),
            "schedule": meta.get("schedule"),
            "files": list(FILES) + ["meta.json"],
        }
        (PUBLIC_DATA_DIR / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        finish_run(run_id, "failed", error=str(exc))
        return 1


def main() -> None:
    argparse.ArgumentParser().parse_args()
    sys.exit(run())


if __name__ == "__main__":
    main()
