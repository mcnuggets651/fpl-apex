#!/usr/bin/env python3
"""Export a write-once, market-independent Apex football-intelligence snapshot."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Match the repository's existing standalone-script convention.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apex_fpl.contracts.football_intelligence import (  # noqa: E402
    FootballIntelligenceContractError,
    build_football_intelligence_snapshot,
    write_football_intelligence_snapshot,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export immutable pre-ensemble Apex football primitives from an already-finished "
            "FPL report run. This command does not execute or modify the production engine."
        )
    )
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--producer-commit-sha", required=True)
    parser.add_argument("--season", required=True, help="Competition season, e.g. 2026/27")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=24.0,
        help="Fail closed when the source report is older than this many hours (default: 24)",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        snapshot = build_football_intelligence_snapshot(
            args.report_dir,
            args.snapshot_root,
            producer_commit_sha=args.producer_commit_sha,
            season=args.season,
            max_age_hours=args.max_age_hours,
        )
        write_football_intelligence_snapshot(snapshot, args.output)
    except FootballIntelligenceContractError as exc:
        print(f"football-intelligence export refused: {exc}", file=sys.stderr)
        return 2
    print(
        "exported immutable football intelligence "
        f"{snapshot['artifact_id']} sha256={snapshot['payload_sha256']} to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
