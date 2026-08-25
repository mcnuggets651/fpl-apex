from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.decision_policy_store import store_decision_policy
from apex_fpl.control.forecast_model_store import store_forecast_model
from apex_fpl.control.production_bundle import (
    load_production_decision_bundle,
    store_production_decision_bundle,
)
from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.ids import DecisionPolicyId, GlobalWorldId, ModelArtifactId

from production_bundle_helpers import synthetic_production_bundle


def test_production_bundle_round_trip_binds_complete_direct_decision_lineage(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    fixture = synthetic_production_bundle(store=store)
    bundle = fixture.bundle

    assert str(bundle.bundle_id) == canonical_sha256(bundle.semantic_payload())
    assert store.verify(str(bundle.bundle_id))
    verified = load_production_decision_bundle(bundle.bundle_id, store=store)
    assert verified.bundle == bundle
    assert verified.decision.decision_input.decision_policy_id == bundle.decision_policy_id
    assert verified.forecast.model_artifact_id == bundle.forecast_model_id
    assert verified.robustness_report.decision_id == bundle.decision_id
    assert verified.robustness_report.scenario_set_id == bundle.scenario_set_id


def test_bundle_cannot_swap_policy_without_changing_the_sealed_decision(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    fixture = synthetic_production_bundle(store=store)
    verified = load_production_decision_bundle(fixture.bundle.bundle_id, store=store)
    other_policy = replace(verified.decision_policy, policy_version="2")
    store_decision_policy(other_policy, store=store)

    forged = replace(fixture.bundle, decision_policy_id=other_policy.decision_policy_id)
    with pytest.raises(ValueError, match="DecisionPolicyId does not match DecisionInput"):
        store_production_decision_bundle(forged, store=store)


def test_bundle_cannot_swap_forecast_model_without_changing_forecast(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    fixture = synthetic_production_bundle(store=store)
    verified = load_production_decision_bundle(fixture.bundle.bundle_id, store=store)
    other_model = replace(verified.forecast_model, model_version="2")
    store_forecast_model(other_model, store=store)

    forged = replace(fixture.bundle, forecast_model_id=other_model.model_artifact_id)
    with pytest.raises(ValueError, match="forecast model identity mismatch"):
        store_production_decision_bundle(forged, store=store)


def test_bundle_world_is_cross_bound_to_forecast_and_candidate_universe(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    fixture = synthetic_production_bundle(store=store)
    forged = replace(
        fixture.bundle,
        world_id=GlobalWorldId(
            canonical_sha256({"schema_name": "different-world", "version": 1})
        ),
    )
    with pytest.raises(ValueError, match="candidate universe world"):
        store_production_decision_bundle(forged, store=store)


def test_bundle_requires_replayable_policy_and_model_semantic_artifacts(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    fixture = synthetic_production_bundle(store=store)
    forged_policy = replace(
        fixture.bundle,
        decision_policy_id=DecisionPolicyId(
            canonical_sha256({"schema_name": "missing-policy", "version": 1})
        ),
    )
    with pytest.raises(ValueError, match="dependency failed integrity/replay"):
        store_production_decision_bundle(forged_policy, store=store)

    forged_model = replace(
        fixture.bundle,
        forecast_model_id=ModelArtifactId(
            canonical_sha256({"schema_name": "missing-model", "version": 1})
        ),
    )
    with pytest.raises(ValueError, match="dependency failed integrity/replay"):
        store_production_decision_bundle(forged_model, store=store)


def test_corrupt_bundle_bytes_fail_closed_before_lineage_is_exposed(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    fixture = synthetic_production_bundle(store=store)
    digest = str(fixture.bundle.bundle_id).split(":", 1)[1]
    path = tmp_path / "artifacts" / "objects" / "sha256" / digest[:2] / digest
    path.write_bytes(b"corrupt")

    with pytest.raises(ValueError, match="failed integrity/replay"):
        load_production_decision_bundle(fixture.bundle.bundle_id, store=store)
