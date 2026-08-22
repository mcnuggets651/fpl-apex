#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.services.adversarial_certification import adversarial_certification_blockers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--decision-bundle-id", default="")
    args = parser.parse_args()

    payload = json.loads(args.report.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("adversarial certification report must be a JSON object")
    blockers = list(adversarial_certification_blockers(payload))
    if args.decision_bundle_id and payload.get("decision_bundle_id") != args.decision_bundle_id:
        blockers.append("adversarial audit DecisionBundle does not match certification target")
    blockers = list(dict.fromkeys(blockers))
    if blockers:
        raise SystemExit("ADVERSARIAL CERTIFICATION BLOCKED: " + "; ".join(blockers))
    print(
        "ADVERSARIAL CERTIFICATION READY: "
        f"{len(payload.get('targets') or [])} target perturbations certified"
    )


if __name__ == "__main__":
    main()
