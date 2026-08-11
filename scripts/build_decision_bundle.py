#!/usr/bin/env python3
"""Fetch and project once, then seal the complete Apex decision surface."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.config import load_settings
from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    args = parser.parse_args()

    settings = load_settings()
    output = run_pipeline(
        settings,
        horizon=args.horizon,
        scenario="both",
        force=args.force,
        plan_transfers=True,
    )
    bundle = DecisionBundle.capture(
        output,
        settings,
        Path(args.bundle_dir),
        repo_root=Path(__file__).resolve().parents[1],
    )
    print(json.dumps(bundle.lineage_summary(), indent=2))


if __name__ == "__main__":
    main()
