#!/usr/bin/env python3
"""Run the isolated V2 reference solver over one sealed request file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.reference_solver_io import request_from_payload
from apex_fpl.workers.reference_solver import solve_reference_request


def _request_payload(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("reference solver request file must be JSON object")
    if document.get("schema_name") == "apex-stored-reference-solver-request":
        if document.get("schema_version") != 1 or not isinstance(document.get("payload"), dict):
            raise ValueError("stored reference solver request envelope is invalid")
        payload = document["payload"]
    else:
        payload = document
    if not isinstance(payload, dict):
        raise ValueError("reference solver request payload must be object")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    request = request_from_payload(_request_payload(args.request))
    run = solve_reference_request(request)
    envelope = {
        "schema_name": "apex-stored-reference-solver-run",
        "schema_version": 1,
        "run_id": run.run_id,
        "payload": run.semantic_payload(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(envelope))
    print(
        f"reference solver {run.solver_status.value}: "
        f"nodes={run.nodes_evaluated} actions={run.actions_evaluated} run={run.run_id}"
    )


if __name__ == "__main__":
    main()
