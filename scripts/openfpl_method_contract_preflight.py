#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from apex.forecast.openfpl_current import training_policy_sha256
from apex.forecast.openfpl_governance import (
    method_contract_sha256,
    validate_method_contract,
)

ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return payload


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate governed OpenFPL-method derivative contract."
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=ROOT / "config/openfpl_method_contract.yaml",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=ROOT / "config/openfpl_training_policy.yaml",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    contract_path = (
        args.contract if args.contract.is_absolute() else ROOT / args.contract
    )
    policy_path = args.policy if args.policy.is_absolute() else ROOT / args.policy
    contract = _load_yaml(contract_path)
    policy = _load_yaml(policy_path)
    locks = json.loads(
        (ROOT / "upstreams.lock.json").read_text(encoding="utf-8")
    )
    errors = validate_method_contract(contract, policy, locks)

    report = {
        "schema_version": 2,
        "contract_id": contract.get("contract_id"),
        "provider_family": contract.get("provider_family"),
        "implementation_id": contract.get("implementation_id"),
        # These are semantic governance identities and therefore canonicalize the
        # parsed mappings. Pure YAML formatting/order changes do not change them.
        "contract_sha256": method_contract_sha256(contract),
        "training_policy_sha256": training_policy_sha256(policy),
        # Raw file digests remain useful forensic evidence but are not model-binding
        # governance identities.
        "contract_file_sha256": _file_sha256(contract_path),
        "training_policy_file_sha256": _file_sha256(policy_path),
        "digest_semantics": "canonical-json-semantic-v1",
        "valid": not errors,
        "errors": list(errors),
        "reference_reproducibility_scope": "INFERENCE_ONLY",
        "exact_upstream_training_reproduction_claim": False,
        "construction_state": (
            "BLOCKED_BY_CURRENT_RULE_HISTORY_AND_EQUIVALENCE_GATES"
        ),
        "serve_authorized": False,
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
