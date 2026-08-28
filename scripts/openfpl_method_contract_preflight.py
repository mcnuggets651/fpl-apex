#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_contract(
    contract: dict[str, Any],
    policy: dict[str, Any],
    locks: dict[str, Any],
) -> tuple[str, ...]:
    errors: list[str] = []

    if contract.get("schema_version") != 1:
        errors.append("method contract schema_version must be 1")
    if contract.get("contract_id") != "apex-openfpl-method-derivative-v1":
        errors.append("unexpected method contract_id")
    if contract.get("provider_family") != "openfpl":
        errors.append("provider_family must remain openfpl")
    if contract.get("implementation_id") != "apex-openfpl-method-derivative":
        errors.append("current implementation must carry derivative identity")
    if contract.get("upstream_reference_identity") != "openfpl-reference-inference":
        errors.append("upstream reference identity must remain inference-only")
    if contract.get("exact_upstream_training_reproduction_claim") is not False:
        errors.append("derivative cannot claim exact upstream training reproduction")

    upstream = locks["sources"]["openfpl"]
    if contract.get("upstream_repository") != upstream.get("repository"):
        errors.append("method contract OpenFPL repository differs from upstream lock")
    if contract.get("upstream_commit") != upstream.get("commit"):
        errors.append("method contract OpenFPL commit differs from upstream lock")

    provenance = contract.get("provenance") or {}
    for key in (
        "upstream_publishes_trained_models",
        "upstream_publishes_inference_code",
        "upstream_publishes_sample_matrix",
    ):
        if provenance.get(key) is not True:
            errors.append(f"provenance {key} must be true for pinned reference")
    for key in (
        "upstream_publishes_sample_construction_pipeline",
        "upstream_publishes_training_pipeline",
    ):
        if provenance.get(key) is not False:
            errors.append(f"provenance {key} must remain false until separately audited")
    if provenance.get("reference_sample_equivalence_required_before_model_build") is not True:
        errors.append("reference sample equivalence must gate model construction")
    independent = provenance.get("independent_semantics_reference") or {}
    dastan = locks["sources"]["dastan"]
    if independent.get("repository") != dastan.get("repository"):
        errors.append("independent semantics reference repository differs from Dastan lock")
    if independent.get("commit") != dastan.get("commit"):
        errors.append("independent semantics reference commit differs from Dastan lock")
    if independent.get("authority") != "non_authoritative_cross_check_only":
        errors.append("Dastan semantics reference must remain non-authoritative")

    if contract.get("scoring_rules_version") != policy.get("scoring_rules_version"):
        errors.append("method and training policy scoring-rules versions differ")
    if contract.get("feature_contract_version") != policy.get("feature_contract_version"):
        errors.append("method and training policy feature-contract versions differ")

    windows = tuple(int(value) for value in (contract.get("history") or {}).get("windows", ()))
    policy_windows = tuple(int(value) for value in policy.get("reference_rolling_windows", ()))
    if windows != (1, 3, 5, 10, 38):
        errors.append("method rolling windows must be exactly 1/3/5/10/38")
    if windows != policy_windows:
        errors.append("method rolling windows differ from governed training policy")
    history = contract.get("history") or {}
    if history.get("current_match_excluded") is not True or history.get("shift_completed_matches") != 1:
        errors.append("rolling history must exclude the current match with a one-match shift")
    if history.get("aggregation") != "arithmetic_mean":
        errors.append("OpenFPL method history aggregation must be arithmetic mean")
    if history.get("future_placeholder_invariance_required") is not True:
        errors.append("future-placeholder invariance must be required")

    excluded = tuple(contract.get("excluded_score_dependent_player_families", ()))
    policy_excluded = tuple(
        str(value).removeprefix("player ")
        for value in policy.get("excluded_score_dependent_feature_families", ())
    )
    if set(excluded) != set(policy_excluded):
        errors.append("method score-dependent exclusions differ from training policy")

    player = contract.get("player_families") or {}
    common = tuple(player.get("common_current", ()))
    goalkeeper = tuple(player.get("goalkeeper_only", ()))
    field = tuple(player.get("field_only", ()))
    for banned in excluded:
        if banned in common or banned in goalkeeper or banned in field:
            errors.append(f"banned scoring-dependent feature remains active: {banned}")

    team_count = len(contract.get("team_families_current", ()))
    opponent_count = len(contract.get("opponent_families_current", ()))
    if team_count != 10 or opponent_count != 10:
        errors.append("current GK/field team and opponent family counts must both be 10")
    position_contract = contract.get("position_feature_contract") or {}
    expected_player_counts = {
        "GK": len(common) + len(goalkeeper),
        "DEF": len(common) + len(field),
        "MID": len(common) + len(field),
        "FWD": len(common) + len(field),
    }
    for position, player_count in expected_player_counts.items():
        row = position_contract.get(position) or {}
        if row.get("player_family_count") != player_count:
            errors.append(f"{position} player family count is inconsistent")
        if row.get("team_family_count") != team_count:
            errors.append(f"{position} team family count is inconsistent")
        if row.get("opponent_family_count") != opponent_count:
            errors.append(f"{position} opponent family count is inconsistent")
        status_count = len(row.get("status_features", ()))
        expected_features = (player_count + team_count + opponent_count) * len(windows) + status_count
        if row.get("current_feature_count") != expected_features:
            errors.append(
                f"{position} feature count must be {expected_features}, got "
                f"{row.get('current_feature_count')}"
            )

    reference = contract.get("reference_sample_matrix") or {}
    identifiers = len(reference.get("identifier_columns", ()))
    statuses = len(reference.get("status_columns", ()))
    rolling = int(reference.get("rolling_feature_columns", -1))
    if identifiers + statuses + rolling != int(reference.get("total_columns", -1)):
        errors.append("reference sample matrix column accounting is inconsistent")
    if int(reference.get("total_columns", -1)) != 235:
        errors.append("pinned OpenFPL reference sample must remain 235 columns")
    reference_family_total = (
        int(reference.get("player_rolling_family_count", -1))
        + int(reference.get("team_rolling_family_count", -1))
        + int(reference.get("opponent_rolling_family_count", -1))
    )
    if reference_family_total * len(windows) != rolling:
        errors.append("reference rolling-family accounting is inconsistent")

    training = contract.get("training") or {}
    if tuple(training.get("positions", ())) != ("GK", "DEF", "MID", "FWD"):
        errors.append("current derivative positions must be GK/DEF/MID/FWD")
    cross_validation = training.get("cross_validation") or {}
    if cross_validation.get("folds") != 5 or cross_validation.get("grouping") != "Premier League team":
        errors.append("training must retain five team-grouped folds")
    bins = (training.get("sample_weighting") or {}).get("bins") or {}
    if bins != {"GK": 2, "DEF": 3, "MID": 4, "FWD": 3}:
        errors.append("position sample-weight bins differ from paper method")
    search = training.get("search") or {}
    if search.get("algorithm") != "K-Best Search" or search.get("population_size") != 10:
        errors.append("K-Best Search population must remain 10")
    ensemble = training.get("ensemble") or {}
    if ensemble.get("top_models_per_fold") != 10 or ensemble.get("folds") != 5:
        errors.append("ensemble must retain top-10 models across five folds")
    if ensemble.get("individual_models_per_position") != 50 or ensemble.get("aggregation") != "median":
        errors.append("ensemble must be median of 50 models per position")

    gates = contract.get("build_gates") or {}
    if gates.get("governed_training_policy") != policy.get("policy_version"):
        errors.append("method contract points to a different training policy")
    if gates.get("minimum_completed_exact_rule_gameweeks") != policy.get("minimum_exact_rule_gameweeks"):
        errors.append("method and policy minimum exact-rule gameweeks differ")
    if gates.get("model_build_before_history_gate") != "forbidden":
        errors.append("model build must be forbidden before history gate")
    if gates.get("serve_authorized") is not False:
        errors.append("method contract cannot authorize serving")
    if gates.get("prospective_qualification_required_for_serving") is not True:
        errors.append("prospective qualification must remain required")

    return tuple(dict.fromkeys(errors))


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate governed OpenFPL-method derivative contract.")
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

    contract_path = args.contract if args.contract.is_absolute() else ROOT / args.contract
    policy_path = args.policy if args.policy.is_absolute() else ROOT / args.policy
    contract = _load_yaml(contract_path)
    policy = _load_yaml(policy_path)
    locks = json.loads((ROOT / "upstreams.lock.json").read_text(encoding="utf-8"))
    errors = validate_contract(contract, policy, locks)

    report = {
        "schema_version": 1,
        "contract_id": contract.get("contract_id"),
        "provider_family": contract.get("provider_family"),
        "implementation_id": contract.get("implementation_id"),
        "contract_sha256": _sha256(contract_path),
        "training_policy_sha256": _sha256(policy_path),
        "valid": not errors,
        "errors": list(errors),
        "reference_reproducibility_scope": "INFERENCE_ONLY",
        "exact_upstream_training_reproduction_claim": False,
        "construction_state": "BLOCKED_BY_CURRENT_RULE_HISTORY_AND_EQUIVALENCE_GATES",
        "serve_authorized": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
