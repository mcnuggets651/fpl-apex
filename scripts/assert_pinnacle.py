#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.services.pinnacle_readiness import evaluate_pinnacle_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Fail unless an Apex Pinnacle snapshot is decision-ready.")
    parser.add_argument("snapshot", nargs="?", default="data/generated/pinnacle_latest.json")
    args = parser.parse_args()

    path = Path(args.snapshot)
    if not path.exists():
        raise SystemExit(f"PINNACLE GATE: BLOCKED - missing snapshot {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = evaluate_pinnacle_payload(payload)
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    if not result.ready:
        print("PINNACLE GATE: BLOCKED")
        for blocker in result.blockers:
            print(f"- {blocker}")
        raise SystemExit(1)
    print("PINNACLE GATE: READY")


if __name__ == "__main__":
    main()
