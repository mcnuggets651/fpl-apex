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

from datetime import datetime, timezone


BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
ROOT = Path(__file__).resolve().parents[1]


def _actionable_gameweeks(
    events: list[dict], horizon: int, *, now: datetime | None = None
) -> list[int]:
    """Match Apex's deadline-aware horizon without crossing the season boundary."""
    now = now or datetime.now(timezone.utc)
    open_ids = []
    for event in events:
        deadline = event.get("deadline_time")
        if not deadline:
            continue
        parsed = datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
        if parsed > now:
            open_ids.append(int(event["id"]))
    if open_ids:
        return sorted(open_ids)[:horizon]

    # Keep a defensive fallback for upstream/bootstrap fixtures without deadlines.
    # Select only real official events: range(start, start+horizon) would fabricate
    # Gameweeks at the end of the season.
    unfinished = sorted(
        int(event["id"]) for event in events if not event.get("finished", False)
    )
    return unfinished[:horizon]


def _official_horizon(horizon: int) -> tuple[list[int], set[int]]:
    request = urllib.request.Request(
        BOOTSTRAP_URL,
        headers={"User-Agent": "apex-fpl-airsenal-worker/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)

    gameweeks = _actionable_gameweeks(payload["events"], horizon)
    if not gameweeks:
        raise SystemExit("No actionable official FPL Gameweeks remain")
    if gameweeks != list(range(gameweeks[0], gameweeks[-1] + 1)):
        raise SystemExit(f"Official FPL returned a non-contiguous horizon: {gameweeks}")
    official_ids = {int(player["id"]) for player in payload["elements"]}
    return gameweeks, official_ids


def _airsenal_pin() -> str:
    lock = json.loads((ROOT / "upstreams.lock.json").read_text(encoding="utf-8"))
    return str(lock["sources"]["airsenal"]["commit"])


def _assert_export_contract(
    output: Path, official_ids: set[int], requested_gameweeks: list[int]
) -> None:
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("AIrsenal export is empty")
    exported = {int(row["player_id"]) for row in rows}
    unknown = sorted(exported - official_ids)
    if unknown:
        raise SystemExit(f"AIrsenal export contains unknown official FPL IDs: {unknown[:10]}")
    covered = {int(row["gw"]) for row in rows}
    missing = sorted(set(requested_gameweeks) - covered)
    if missing:
        raise SystemExit(f"AIrsenal export is missing requested Gameweeks: {missing}")


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

    gameweeks, official_ids = _official_horizon(args.horizon)
    start = gameweeks[0]
    # Pinned AIrsenal's gameweek_end is exclusive (Python range semantics).
    end_exclusive = gameweeks[-1] + 1
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
            str(end_exclusive),
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
    _assert_export_contract(args.output, official_ids, gameweeks)
    print(
        f"Generated genuine AIrsenal forecast for GW{start}-GW{gameweeks[-1]} "
        f"with pinned source {_airsenal_pin()}"
    )


if __name__ == "__main__":
    main()
