from __future__ import annotations

import pytest

from apex.forecast.openfpl_current import (
    CURRENT_SCORING_RULES_VERSION,
    current_model_manifest_errors,
    exact_rule_history_readiness,
)


def _sha(char: str) -> str:
    return char * 64


def current_manifest() -> dict:
    return {
        "provider": "openfpl",
        "provider_version": "current-model-sha",
        "scoring_rules_version": CURRENT_SCORING_RULES_VERSION,
        "source_snapshot": "official-seal",
        "target_gameweek": 2,
        "training_max_gameweek": 1,
        "feature_contract_version": "openfpl-apex-live-v1",
        "model_artifact_sha256": _sha("a"),
        "training_dataset_sha256": _sha("b"),
        "placeholder_invariance": True,
        "official_forecast_coverage": 1.0,
        "legacy_reference_weights_reused": False,
        "serve_authorized": False,
    }


def test_current_openfpl_manifest_can_pass_operational_contract():
    assert current_model_manifest_errors(
        current_manifest(),
        target_gameweek=2,
        source_snapshot="official-seal",
    ) == ()


def test_legacy_openfpl_weights_cannot_be_relabelled_as_current():
    manifest = current_manifest()
    manifest["legacy_reference_weights_reused"] = True
    errors = current_model_manifest_errors(
        manifest,
        target_gameweek=2,
        source_snapshot="official-seal",
    )
    assert any("legacy OpenFPL weights" in error for error in errors)


def test_openfpl_training_must_stop_before_target_gameweek():
    manifest = current_manifest()
    manifest["training_max_gameweek"] = 2
    errors = current_model_manifest_errors(
        manifest,
        target_gameweek=2,
        source_snapshot="official-seal",
    )
    assert any("target/future gameweek" in error for error in errors)


def test_openfpl_must_prove_future_placeholder_invariance():
    manifest = current_manifest()
    manifest["placeholder_invariance"] = False
    errors = current_model_manifest_errors(
        manifest,
        target_gameweek=2,
        source_snapshot="official-seal",
    )
    assert any("leakage audit" in error for error in errors)


def test_openfpl_shadow_cannot_self_authorize_serving():
    manifest = current_manifest()
    manifest["serve_authorized"] = True
    errors = current_model_manifest_errors(
        manifest,
        target_gameweek=2,
        source_snapshot="official-seal",
    )
    assert any("non-serving" in error for error in errors)


def test_exact_rule_history_does_not_invent_training_threshold():
    result = exact_rule_history_readiness((1,), target_gameweek=2)
    assert result["state"] == "TRAINING_POLICY_UNSET"
    assert result["training_ready"] is False
    assert result["exact_rule_gameweek_count"] == 1


def test_exact_rule_history_blocks_target_or_future_leakage():
    result = exact_rule_history_readiness((1, 2), target_gameweek=2)
    assert result["state"] == "HISTORY_LEAKAGE"
    assert result["training_ready"] is False


def test_exact_rule_history_advances_only_against_governed_minimum():
    insufficient = exact_rule_history_readiness(
        (1, 2, 3),
        target_gameweek=4,
        minimum_exact_rule_gameweeks=4,
    )
    ready = exact_rule_history_readiness(
        (1, 2, 3),
        target_gameweek=4,
        minimum_exact_rule_gameweeks=3,
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
