#!/usr/bin/env python3
"""Validate a candidate FPL Core revision before it can replace the live pin."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from apex_fpl.services.core_candidate import validate_core_candidate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", required=True, help="Immutable candidate FPL Core commit SHA")
    parser.add_argument(
        "--season",
        default=os.getenv("APEX_SEASON", "2026-2027"),
        help="Current FPL season (default: APEX_SEASON or 2026-2027)",
    )
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache/core-candidate"))
    args = parser.parse_args()

    summary = validate_core_candidate(args.ref, args.season, args.cache_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
