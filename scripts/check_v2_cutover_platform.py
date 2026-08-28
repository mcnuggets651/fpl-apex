#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from apex.governance.platform import validate_platform_controls

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_policy(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("cutover platform policy must be a mapping")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fail closed unless GitHub platform controls satisfy Apex V2 cutover."
        )
    )
    parser.add_argument("--branch-json", required=True, type=Path)
    parser.add_argument("--rulesets-json", required=True, type=Path)
    parser.add_argument("--immutable-json", required=True, type=Path)
    parser.add_argument("--immutable-status", required=True, type=int)
    parser.add_argument(
        "--policy",
        type=Path,
        default=ROOT / "config/apex_v2_cutover_platform.yaml",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    policy_path = args.policy if args.policy.is_absolute() else ROOT / args.policy
    branch = _load_json(args.branch_json)
    rulesets = _load_json(args.rulesets_json)
    immutable_payload = _load_json(args.immutable_json)
    policy = _load_policy(policy_path)
    if not isinstance(branch, dict):
        raise SystemExit("branch evidence must be a JSON object")
    if not isinstance(rulesets, list):
        raise SystemExit("ruleset evidence must be a JSON array")
    if not isinstance(immutable_payload, dict):
        immutable_payload = {}

    errors = validate_platform_controls(
        branch,
        [row for row in rulesets if isinstance(row, dict)],
        int(args.immutable_status),
        immutable_payload,
        policy,
    )
    report = {
        "schema_version": 1,
        "policy_id": policy.get("policy_id"),
        "default_branch": policy.get("default_branch"),
        "platform_ready": not errors,
        "errors": list(errors),
        "branch_protected": branch.get("protected") is True,
        "active_ruleset_count": sum(
            1
            for row in rulesets
            if isinstance(row, dict) and row.get("enforcement") == "active"
        ),
        "immutable_status_code": int(args.immutable_status),
        "immutable_enabled": (
            isinstance(immutable_payload, dict)
            and immutable_payload.get("enabled") is True
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
