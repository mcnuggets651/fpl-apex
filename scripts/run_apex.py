#!/usr/bin/env python3
"""Run the single canonical Apex decision workflow.

User-facing rule: run this command, then read apex_recommendation_latest.json.
Pinnacle and Elite files are internal diagnostics only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


def _explicit_readiness_block(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    gate = payload.get("pinnacle_gate")
    blockers = gate.get("blockers") if isinstance(gate, dict) else None
    return payload.get("pinnacle_ready") is False and bool(blockers)


def _run(command: list[str]) -> int:
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, check=False).returncode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--stochastic-scenarios", type=int, default=256)
    parser.add_argument("--cvar-alpha", type=float, default=0.10)
    parser.add_argument("--cvar-weight", type=float, default=0.20)
    parser.add_argument("--output-dir", default="data/generated")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    pinnacle_path = output_dir / "pinnacle_latest.json"
    elite_path = output_dir / "elite_latest.json"

    pinnacle_cmd = [
        sys.executable,
        "scripts/run_pinnacle.py",
        "--horizon",
        str(args.horizon),
        "--stochastic-scenarios",
        str(args.stochastic_scenarios),
        "--cvar-alpha",
        str(args.cvar_alpha),
        "--cvar-weight",
        str(args.cvar_weight),
        "--output-dir",
        str(output_dir),
    ]
    if args.force:
        pinnacle_cmd.append("--force")

    status = _run(pinnacle_cmd)
    if status != 0 and not _explicit_readiness_block(pinnacle_path):
        raise SystemExit(status)

    # Deliberately do not force-refresh again. Elite must consume the cached source
    # surface created by Pinnacle so the canonical builder can require identical
    # official snapshot identity.
    elite_status = _run(
        [
            sys.executable,
            "scripts/run_elite.py",
            "--horizon",
            str(args.horizon),
            "--output-dir",
            str(output_dir),
        ]
    )
    if elite_status != 0:
        raise SystemExit(elite_status)

    canonical_status = _run(
        [
            sys.executable,
            "scripts/build_canonical_recommendation.py",
            "--pinnacle",
            str(pinnacle_path),
            "--elite",
            str(elite_path),
            "--output-dir",
            str(output_dir),
        ]
    )
    raise SystemExit(canonical_status)


if __name__ == "__main__":
    main()
