from __future__ import annotations

from apex.forecast.openfpl_current import (
    CURRENT_SCORING_RULES_VERSION,
    current_model_manifest_errors,
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
