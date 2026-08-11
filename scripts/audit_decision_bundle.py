#!/usr/bin/env python3
"""Validate and print the complete lineage of a sealed decision bundle."""
from __future__ import annotations

import argparse
import json

from apex_fpl.services.decision_bundle import DecisionBundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "bundle_dir",
        nargs="?",
        default="data/generated/decision_bundle",
    )
    args = parser.parse_args()
    bundle = DecisionBundle.load(args.bundle_dir)
    print(json.dumps(bundle.lineage_summary(), indent=2))


if __name__ == "__main__":
    main()
