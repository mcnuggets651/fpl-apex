#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.services.answer_context import build_answer_context


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", default="data/generated/apex_recommendation_latest.json")
    parser.add_argument("--pinnacle", default="data/generated/pinnacle_latest.json")
    parser.add_argument("--output", default="data/generated/apex_answer_context.json")
    args = parser.parse_args()
    context = build_answer_context(_load(Path(args.canonical)), _load(Path(args.pinnacle)))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(context, indent=2), encoding="utf-8")
    raise SystemExit(0 if context["safe_to_act"] else 2)


if __name__ == "__main__":
    main()
