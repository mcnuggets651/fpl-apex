#!/usr/bin/env python3
"""Replay all Apex decision layers from a sealed bundle without live retrieval."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from apex_fpl.services.decision_bundle import DecisionBundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "bundle_dir",
        nargs="?",
        default="data/generated/decision_bundle",
    )
    parser.add_argument("--output-dir", default="data/generated/replay")
    parser.add_argument("--stochastic-scenarios", type=int, default=256)
    parser.add_argument("--cvar-alpha", type=float, default=0.10)
    parser.add_argument("--cvar-weight", type=float, default=0.20)
    args = parser.parse_args()

    bundle = DecisionBundle.load(args.bundle_dir)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "scripts/run_apex.py",
        "--reuse-bundle",
        "--horizon",
        str(len(bundle.manifest["gameweeks"])),
        "--bundle-dir",
        str(bundle.root),
        "--output-dir",
        str(output),
        "--stochastic-scenarios",
        str(args.stochastic_scenarios),
        "--cvar-alpha",
        str(args.cvar_alpha),
        "--cvar-weight",
        str(args.cvar_weight),
    ]
    raise SystemExit(subprocess.run(command, check=False).returncode)


if __name__ == "__main__":
    main()
