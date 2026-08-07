#!/usr/bin/env python3
"""Run pinned AIrsenal predictions and export the official-FPL-ID contract."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request


BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
ROOT = Path(__file__).resolve().parents[1]


def _official_horizon(horizon: int) -> tuple[int, int, set[int]]:
    request = urllib.request.Request(
        BOOTSTRAP_URL,
        headers={"User-Agent": "apex-fpl-airsenal-worker/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)

    unfinished = sorted(
        int(event["id"])
        for event in payload["events"]
        if not event.get("finished", False)
    )
    if not unfinished:
        raise SystemExit("No unfinished official FPL Gameweeks remain")
    official_ids = {int(player["id"]) for player in payload["elements"]}
    start = unfinished[0]
    return start, min(38, start + horizon - 1), official_ids


def _airsenal_pin() -> str:
    lock = json.loads((ROOT / "upstreams.lock.json").read_text(encoding="utf-8"))
    return str(lock["sources"]["airsenal"]["commit"])


def _assert_official_ids(output: Path, official_ids: set[int]) -> None:
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("AIrsenal export is empty")
    exported = {int(row["player_id"]) for row in rows}
    unknown = sorted(exported - official_ids)
    if unknown:
        raise SystemExit(f"AIrsenal export contains unknown official FPL IDs: {unknown[:10]}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate genuine pinned AIrsenal forecasts for the live FPL horizon."
    )
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.horizon < 1:
        parser.error("--horizon must be positive")
    if not args.db.is_file() or args.db.stat().st_size == 0:
        raise SystemExit(f"AIrsenal database is missing or empty: {args.db}")

    start, end, official_ids = _official_horizon(args.horizon)
    env = {
        **os.environ,
        "AIRSENAL_DB_FILE": str(args.db.resolve()),
        "AIRSENAL_SOURCE_VERSION": _airsenal_pin(),
    }
    subprocess.run(
        [
            "airsenal_run_prediction",
            "--gameweek_start",
            str(start),
            "--gameweek_end",
            str(end),
        ],
        check=True,
        env=env,
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "export_airsenal.py"),
            str(args.db),
            "LATEST",
            str(args.output),
        ],
        check=True,
        env=env,
    )
    _assert_official_ids(args.output, official_ids)
    print(
        f"Generated genuine AIrsenal forecast for GW{start}-GW{end} "
        f"with pinned source {_airsenal_pin()}"
    )


if __name__ == "__main__":
    main()
