from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.evaluation.bench_appearance_shadow import run_bench_appearance_shadow


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated bench-appearance shadow audit.")
    parser.add_argument("--core-root", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/historical/preseason_validation_sources.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/bench_appearance_shadow.json"),
    )
    args = parser.parse_args()

    payload = run_bench_appearance_shadow(args.core_root, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
