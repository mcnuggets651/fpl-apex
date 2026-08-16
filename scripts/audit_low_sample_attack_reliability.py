#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.evaluation.low_sample_attack import run_low_sample_attack_audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    report = run_low_sample_attack_audit(
        Path(args.core_root),
        Path(args.manifest),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if report["result"] != "improves_or_neutral":
        raise SystemExit(
            "low-sample attack reliability gate did not pass: " + report["result"]
        )


if __name__ == "__main__":
    main()
