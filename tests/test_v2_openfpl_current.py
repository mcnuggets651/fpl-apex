from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from apex.forecast.openfpl_current import (
    CURRENT_FEATURE_CONTRACT_VERSION,
    CURRENT_IMPLEMENTATION_ID,
    CURRENT_MINIMUM_EXACT_RULE_GAMEWEEKS,
    CURRENT_SCORING_RULES_VERSION,
    CURRENT_TRAINING_POLICY_VERSION,
    CURRENT_UPSTREAM_REFERENCE_ID,
    current_model_manifest_errors,
    exact_rule_history_readiness,
    score_dependent_feature_columns,
    training_policy_errors,
    training_policy_sha256,
)

ROOT = Path(__file__).resolve().parents[1]


def _sha(char: str) -> str:
    return char * 64


def governed_policy() -> dict:
    return yaml.safe_load(
        (ROOT / "config/openfpl_training_policy.yaml").read_text(encoding="utf-8")
    )


def method_contract_sha256() -> str:
    return hashlib.sha256(
        (ROOT / "config/openfpl_method_contract.yaml").read_bytes()
    ).hexdigest()


def current_manifest() -> dict:
    return {
        "provider": "openfpl",
        "provider_version": "current-model-sha",
        "implementation_id": CURRENT_IMPLEMENTATION_ID,
        "upstream_reference_identity": CURRENT_UPSTREAM_REFERENCE_ID,
        "exact_upstream_training_reproduction_claim": False,
        "scoring_rules_version": CURRENT_SCORING_RULES_VERSION,
        "source_snapshot": "official-seal",
        "target_gameweek": 11,
        "training_max_gameweek": 10,
        "training_policy_version": CURRENT_TRAINING_POLICY_VERSION,
        "training_policy_sha256": training_policy_sha256(governed_policy()),
        "method_contract_sha256": method_contract_sha256(),
        "minimum_exact_rule_gameweeks": CURRENT_MINIMUM_EXACT_RULE_GAMEWEEKS,
        "exact_rule_gameweeks": list(range(1, 11)),
        "feature_contract_version": CURRENT_FEATURE_CONTRACT_VERSION,
        "feature_construction_validation": True,
        "reference_sample_semantics_validation": True,
        "model_artifact_sha256": _sha("a"),
        "training_dataset_sha256": _sha("b"),
        "placeholder_invariance": True,
        "official_forecast_coverage": 1.0,
        "legacy_reference_weights_reused": False,
        "serve_authorized": False,
    }


def manifest_errors(manifest: dict) -> tuple[str, ...]:
    return current_model_manifest_errors(
        manifest,
        target_gameweek=11,
        source_snapshot="official-seal",
        expected_training_policy_sha256=training_policy_sha256(governed_policy()),
        expected_method_contract_sha256=method_contract_sha256(),
    )


def test_governed_openfpl_training_policy_is_self_consistent():
    policy = governed_policy()
    assert training_policy_errors(policy) == ()
    assert policy["minimum_exact_rule_gameweeks"] == 10
    assert policy["policy_version"] == CURRENT_TRAINING_POLICY_VERSION
    assert policy["feature_contract_version"] == CURRENT_FEATURE_CONTRACT_VERSION
    identity = policy["implementation_identity"]
    assert identity["current_rules_identity"] == CURRENT_IMPLEMENTATION_ID
    assert identity["upstream_reference_identity"] == CURRENT_UPSTREAM_REFERENCE_ID
    assert identity["exact_upstream_training_reproduction_claim"] is False
    assert len(training_policy_sha256(policy)) == 64


def test_current_openfpl_manifest_can_pass_operational_contract_after_history_floor():
    assert manifest_errors(current_manifest()) == ()


def test_current_manifest_must_use_derivative_implementation_identity():
    manifest = current_manifest()
    manifest["implementation_id"] = "openfpl"
    errors = manifest_errors(manifest)
    assert any("current implementation must be" in error for error in errors)


def test_current_manifest_must_identify_inference_only_upstream_reference():
    manifest = current_manifest()
    manifest["upstream_reference_identity"] = "openfpl-upstream-trainer"
    errors = manifest_errors(manifest)
    assert any("upstream reference identity must be" in error for error in errors)


def test_current_manifest_cannot_claim_exact_upstream_training_reproduction():
    manifest = current_manifest()
    manifest["exact_upstream_training_reproduction_claim"] = True
    errors = manifest_errors(manifest)
    assert any("cannot claim exact upstream training reproduction" in error for error in errors)


def test_current_openfpl_manifest_must_bind_exact_governed_policy_hash():
    manifest = current_manifest()
    manifest["training_policy_sha256"] = _sha("c")
    errors = manifest_errors(manifest)
    assert any("different governed policy hash" in error for error in errors)


def test_current_openfpl_manifest_must_bind_exact_governed_method_hash():
    manifest = current_manifest()
    manifest["method_contract_sha256"] = _sha("c")
    errors = manifest_errors(manifest)
    assert any("different governed method-contract hash" in error for error in errors)


def test_current_openfpl_manifest_must_use_governed_feature_contract():
    manifest = current_manifest()
    manifest["feature_contract_version"] = "legacy-reference-features"
    errors = manifest_errors(manifest)
    assert any("feature contract" in error for error in errors)


def test_current_model_requires_independent_feature_construction_validation():
    manifest = current_manifest()
    manifest["feature_construction_validation"] = False
    errors = manifest_errors(manifest)
    assert any("feature construction" in error for error in errors)


def test_current_model_requires_reference_sample_semantics_validation():
    manifest = current_manifest()
    manifest["reference_sample_semantics_validation"] = False
    errors = manifest_errors(manifest)
    assert any("reference-sample semantics" in error for error in errors)


def test_legacy_openfpl_weights_cannot_be_relabelled_as_current():
    manifest = current_manifest()
    manifest["legacy_reference_weights_reused"] = True
    errors = manifest_errors(manifest)
    assert any("legacy OpenFPL weights" in error for error in errors)


def test_openfpl_training_must_stop_before_target_gameweek():
    manifest = current_manifest()
    manifest["training_max_gameweek"] = 11
    manifest["exact_rule_gameweeks"] = list(range(1, 12))
    errors = manifest_errors(manifest)
    assert any("target/future gameweek" in error for error in errors)


def test_openfpl_model_requires_exact_governed_training_policy_version():
    manifest = current_manifest()
    manifest["training_policy_version"] = ""
    errors = manifest_errors(manifest)
    assert any("training policy version must be" in error for error in errors)


def test_openfpl_model_requires_governed_history_floor_to_be_met():
    manifest = current_manifest()
    manifest["exact_rule_gameweeks"] = list(range(1, 10))
    manifest["training_max_gameweek"] = 9
    errors = manifest_errors(manifest)
    assert any("governed minimum is 10" in error for error in errors)


def test_openfpl_model_cannot_lower_governed_history_floor():
    manifest = current_manifest()
    manifest["minimum_exact_rule_gameweeks"] = 1
    errors = manifest_errors(manifest)
    assert any("governed floor 10" in error for error in errors)


def test_openfpl_model_training_max_must_match_declared_exact_history():
    manifest = current_manifest()
    manifest["training_max_gameweek"] = 9
    errors = manifest_errors(manifest)
    assert any("maximum declared exact-rule gameweek" in error for error in errors)


def test_openfpl_must_prove_future_placeholder_invariance():
    manifest = current_manifest()
    manifest["placeholder_invariance"] = False
    errors = manifest_errors(manifest)
    assert any("leakage audit" in error for error in errors)


def test_openfpl_shadow_cannot_self_authorize_serving():
    manifest = current_manifest()
    manifest["serve_authorized"] = True
    errors = manifest_errors(manifest)
    assert any("non-serving" in error for error in errors)


def test_feature_contract_detects_every_score_dependent_reference_family():
    columns = (
        "player fpl points 1",
        "player relevant fpl points 10",
        "player bps 5",
        "player fpl bonus points 38",
        "player expected goals 5",
        "team elo",
    )
    assert score_dependent_feature_columns(columns) == columns[:4]


def test_feature_contract_normalises_underscores_and_case():
    columns = ("PLAYER_FPL_POINTS_3", "Player_BPS_10", "player_xg_3")
    assert score_dependent_feature_columns(columns) == columns[:2]


def test_policy_rejects_missing_score_dependent_exclusion():
    policy = governed_policy()
    policy["excluded_score_dependent_feature_families"] = ["player fpl points"]
    errors = training_policy_errors(policy)
    assert any("does not exclude all legacy scoring" in error for error in errors)


def test_policy_rejects_upstream_reproduction_claim():
    policy = governed_policy()
    policy["implementation_identity"]["exact_upstream_training_reproduction_claim"] = True
    errors = training_policy_errors(policy)
    assert any("cannot claim exact upstream training reproduction" in error for error in errors)


def test_exact_rule_history_without_loaded_policy_fails_closed():
    result = exact_rule_history_readiness((1,), target_gameweek=2)
    assert result["state"] == "TRAINING_POLICY_UNSET"
    assert result["training_ready"] is False
    assert result["exact_rule_gameweek_count"] == 1


def test_exact_rule_history_blocks_target_or_future_leakage():
    result = exact_rule_history_readiness(
        (1, 2),
        target_gameweek=2,
        minimum_exact_rule_gameweeks=CURRENT_MINIMUM_EXACT_RULE_GAMEWEEKS,
    )
    assert result["state"] == "HISTORY_LEAKAGE"
    assert result["training_ready"] is False


def test_exact_rule_history_advances_only_against_governed_minimum():
    insufficient = exact_rule_history_readiness(
        tuple(range(1, 10)),
        target_gameweek=10,
        minimum_exact_rule_gameweeks=CURRENT_MINIMUM_EXACT_RULE_GAMEWEEKS,
    )
    ready = exact_rule_history_readiness(
        tuple(range(1, 11)),
        target_gameweek=11,
        minimum_exact_rule_gameweeks=CURRENT_MINIMUM_EXACT_RULE_GAMEWEEKS,
    )
    assert insufficient["state"] == "CURRENT_LABEL_HISTORY_INSUFFICIENT"
    assert insufficient["training_ready"] is False
    assert ready["state"] == "CURRENT_LABEL_HISTORY_READY"
    assert ready["training_ready"] is True


def test_exact_rule_history_rejects_invalid_governed_minimum():
    with pytest.raises(ValueError, match=">= 1"):
        exact_rule_history_readiness(
            (1,),
            target_gameweek=2,
            minimum_exact_rule_gameweeks=0,
        )
