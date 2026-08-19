#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.statistical_truth import audit_statistical_truth


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument("--output", default="reports/statistical_truth_audit.json")
    args = parser.parse_args()

    bundle = DecisionBundle.load(args.bundle_dir)
    out = bundle.to_pipeline_output()
    expected = int(len(out.players))
    audit = audit_statistical_truth(
        out.players,
        out.projections,
        expected_players=expected,
        as_of=bundle.created_at,
    )
    audit["decision_bundle_id"] = bundle.bundle_id
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))
    raise SystemExit(0 if audit["ready"] else 1)


if __name__ == "__main__":
    main()
