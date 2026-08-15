"""Report whether projection-policy challengers have enough history to be promoted.

This CLI is deliberately fail-closed: it records missing replay/preseason evidence
without changing fixture decay, preseason attacking rates, or the minutes model.
Raw cumulative xP remains a forecast quantity; any decayed horizon value is reported
only as decision utility and can never be promoted merely by changing its label.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.evaluation.projection_policy_readiness import (
    build_projection_policy_readiness,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apex-store", type=Path, required=True)
    parser.add_argument("--core-root", type=Path, required=True)
    parser.add_argument("--historical-audit", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = build_projection_policy_readiness(
        args.apex_store,
        args.core_root,
        historical_audit_path=args.historical_audit,
    )
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
