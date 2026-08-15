from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.evaluation.historical_minutes_preseason import run_historical_minutes_audit


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run shadow historical preseason/minutes calibration audit."
    )
    parser.add_argument("--core-root", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/historical/preseason_validation_sources.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/historical_minutes_preseason.json"),
    )
    args = parser.parse_args()

    result = run_historical_minutes_audit(args.core_root, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
