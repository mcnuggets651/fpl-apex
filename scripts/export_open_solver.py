#!/usr/bin/env python3
"""Export a sealed Apex DecisionBundle to the pinned open-solver CSV contract."""
from __future__ import annotations

import argparse
from pathlib import Path

from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.open_solver_export import export_bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--projection-col", default="xp")
    args = parser.parse_args()
    export_bundle(
        DecisionBundle.load(args.bundle_dir),
        args.output,
        args.projection_col,
    )


if __name__ == "__main__":
    main()
