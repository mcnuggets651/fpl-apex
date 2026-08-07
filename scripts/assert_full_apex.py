#!/usr/bin/env python3
from __future__ import annotations

import argparse

from apex_fpl.services.readiness import load_and_evaluate


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fail unless an Apex report is safe-to-act and fully production-ready."
    )
    parser.add_argument("report", nargs="?", default="reports/latest.json")
    args = parser.parse_args()

    result = load_and_evaluate(args.report)
    if not result.ready:
        print("FULL APEX GATE: BLOCKED")
        for blocker in result.blockers:
            print(f"- {blocker}")
        raise SystemExit(1)
    print("FULL APEX GATE: READY")


if __name__ == "__main__":
    main()
