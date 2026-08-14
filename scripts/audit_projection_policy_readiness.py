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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = build_projection_policy_readiness(args.apex_store, args.core_root)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
