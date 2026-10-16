#!/usr/bin/env python3
"""Run pipeline steps A → B → C → E → D in order."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    import os

    os.environ.setdefault("PYTHONPATH", str(ROOT))
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Offline fixtures for trends/rankings")
    parser.add_argument("--csv-only", action="store_true", help="Skip Product Hunt fetch")
    args = parser.parse_args()

    trends_cmd = [sys.executable, "-m", "scripts.ingest_trends"] + (["--demo"] if args.demo else [])
    rankings_cmd = (
        [sys.executable, "-m", "scripts.ingest_rankings"]
        + (["--demo"] if args.demo else [])
        + (["--csv-only"] if args.csv_only else [])
    )
    steps = [
        ("ingest_trends", trends_cmd, True),
        ("ingest_rankings", rankings_cmd, False),
        ("build_opportunity_cards", [sys.executable, "-m", "scripts.build_opportunity_cards"], False),
        ("build_weekly_movers", [sys.executable, "-m", "scripts.build_weekly_movers"], False),
        ("publish_site", [sys.executable, "-m", "scripts.publish_site"], False),
    ]
    for name, cmd, allow_trends_demo_fallback in steps:
        print(">>", " ".join(cmd), flush=True)
        rc = subprocess.call(cmd, cwd=str(ROOT), env=env)
        if rc != 0 and allow_trends_demo_fallback and os.environ.get("TRENDS_FALLBACK_DEMO") == "1" and not args.demo:
            print(">> Trends live failed; falling back to --demo (TRENDS_FALLBACK_DEMO=1)", flush=True)
            fallback = [sys.executable, "-m", "scripts.ingest_trends", "--demo"]
            rc = subprocess.call(fallback, cwd=str(ROOT), env=env)
            if rc == 0:
                from scripts.lib.runs import finish_run, start_run

                rid = start_run(
                    "ingest_trends",
                    {"source": "demo", "trends_fallback_demo": True, "note": "live Google Trends failed"},
                )
                finish_run(rid, "partial", counts={}, error="Live Trends unavailable; used fixtures")
        if rc != 0:
            sys.exit(rc)
    print("Pipeline complete.", flush=True)


if __name__ == "__main__":
    main()
