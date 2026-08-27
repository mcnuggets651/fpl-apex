from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.champion_authority import (
    create_production_champion_generation,
    issue_champion_admission,
    load_production_champion_generation,
    verify_bundle_champion_authority,
)
from apex_fpl.control.production_planning_bundle import load_production_planning_bundle
from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.champion_authority import ChampionRole

from champion_authority_helpers import synthetic_production_champion_authority
from empirical_qualification_helpers import synthetic_supported_qualification_artifact
from production_planning_bundle_helpers import synthetic_production_planning_bundle


def _store(tmp_path: Path) -> FileSystemArtifactStore:
    return FileSystemArtifactStore(tmp_path / "artifacts")


def test_champion_authority_replays_all_four_bundle_champions(tmp_path: Path) -> None:
    store = _store(tmp_path)
    fixture = synthetic_production_planning_bundle(store=store)
    authority = synthetic_production_champion_authority(store=store, fixture=fixture)
    verified = load_production_planning_bundle(fixture.bundle.bundle_id, store=store)

    replayed = verify_bundle_champion_authority(
        authority.generation.artifact_id,
        verified_bundle=verified,
        as_of="2026-08-24T12:00:00Z",
        store=store,
    )

    generation = replayed.generation
    assert generation.forecast_model_id == str(verified.forecast_model.model_artifact_id)
    assert generation.decision_policy_id == str(verified.decision_policy.decision_policy_id)
    assert generation.scenario_generator_id == str(verified.scenario_set.scenario_generator_id)
    assert generation.scenario_policy_id == str(verified.robustness_report.scenario_policy_id)


def test_champion_generation_rejects_stale_writer(tmp_path: Path) -> None:
    store = _store(tmp_path)
    fixture = synthetic_production_planning_bundle(store=store)
    first = synthetic_production_champion_authority(store=store, fixture=fixture)

    with pytest.raises(ValueError, match="stale champion-generation writer"):
        synthetic_production_champion_authority(
            store=store,
            fixture=fixture,
            current_generation_artifact_id=first.generation.artifact_id,
            expected_parent_generation_id="sha256:" + "0" * 64,
        )


def test_champion_admission_requires_retained_review_evidence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    fixture = synthetic_production_planning_bundle(store=store)
    payload = {
        "schema_name": "synthetic-planning-generator",
        "season": fixture.bundle.season,
    }
    candidate_id = canonical_sha256(payload)
    qualification = synthetic_supported_qualification_artifact(
        store=store,
        subject_payload=payload,
        subject_kind="apex.scenario-generator",
        proof_id="QUAL-SCENARIO-GENERATOR-001",
        season=fixture.bundle.season,
    )

    with pytest.raises(ValueError, match="review evidence is missing/corrupt"):
        issue_champion_admission(
            role=ChampionRole.SCENARIO_GENERATOR,
            season=fixture.bundle.season,
            candidate_id=candidate_id,
            subject_payload=payload,
            qualification_artifact_id=qualification,
            review_artifact_id="sha256:" + "1" * 64,
            reviewed_by="reviewer",
            reviewed_at="2026-08-24T12:00:00Z",
            reason="must fail without retained review evidence",
            store=store,
        )


def test_bundle_replay_rejects_different_authorized_scenario_generator(tmp_path: Path) -> None:
    store = _store(tmp_path)
    fixture = synthetic_production_planning_bundle(store=store)
    baseline = synthetic_production_champion_authority(store=store, fixture=fixture)
    wrong_payload = {
        "schema_name": "synthetic-other-generator",
        "season": fixture.bundle.season,
    }
    wrong_id = canonical_sha256(wrong_payload)
    wrong_qualification = synthetic_supported_qualification_artifact(
        store=store,
        subject_payload=wrong_payload,
        subject_kind="apex.scenario-generator",
        proof_id="QUAL-SCENARIO-GENERATOR-001",
        season=fixture.bundle.season,
    )
    wrong_admission = issue_champion_admission(
        role=ChampionRole.SCENARIO_GENERATOR,
        season=fixture.bundle.season,
        candidate_id=wrong_id,
        subject_payload=wrong_payload,
        qualification_artifact_id=wrong_qualification,
        review_artifact_id=store.put_bytes(b"reviewed wrong generator for negative test").artifact_id,
        reviewed_by="negative-test-reviewer",
        reviewed_at="2026-08-24T12:00:00Z",
        reason="negative-test alternate authorized generator",
        store=store,
    )
    alternate = create_production_champion_generation(
        season=fixture.bundle.season,
        forecast_registry_generation_artifact_id=(
            baseline.forecast_registry_generation_artifact_id
        ),
        decision_policy_admission_artifact_id=baseline.decision_policy_admission.artifact_id,
        scenario_generator_admission_artifact_id=wrong_admission.artifact_id,
        scenario_policy_admission_artifact_id=baseline.scenario_policy_admission.artifact_id,
        change_control_artifact_id=store.put_bytes(b"alternate generation change control").artifact_id,
        authorized_by="negative-test-authorizer",
        authorized_at="2026-08-24T12:00:00Z",
        reason="negative-test alternate generation",
        current_generation_artifact_id=None,
        expected_parent_generation_id=None,
        store=store,
    )
    verified = load_production_planning_bundle(fixture.bundle.bundle_id, store=store)

    with pytest.raises(ValueError, match="scenario generator"):
        verify_bundle_champion_authority(
            alternate.artifact_id,
            verified_bundle=verified,
            as_of="2026-08-24T12:00:00Z",
            store=store,
        )


def test_decision_policy_admission_binds_exact_qualification_artifact(tmp_path: Path) -> None:
    store = _store(tmp_path)
    fixture = synthetic_production_planning_bundle(store=store)
    policy_id = str(fixture.bundle.decision_policy_id)
    import json

    payload = json.loads(store.read_bytes(policy_id).decode("utf-8"))
    assert isinstance(payload, dict)
    other_qualification = synthetic_supported_qualification_artifact(
        store=store,
        subject_payload={
            **payload,
            "qualification_state": "SHADOW",
            "qualification_artifact_id": None,
        },
        subject_kind="apex.decision-policy",
        proof_id="PO-DECISION-POLICY-QUALIFICATION-001",
        season=fixture.bundle.season,
        valid_until="2026-10-31T00:00:00Z",
    )
    review = store.put_bytes(b"decision policy review evidence").artifact_id

    with pytest.raises(ValueError, match="does not bind the replayed qualification artifact"):
        issue_champion_admission(
            role=ChampionRole.DECISION_POLICY,
            season=fixture.bundle.season,
            candidate_id=policy_id,
            subject_payload=payload,
            qualification_artifact_id=other_qualification,
            review_artifact_id=review,
            reviewed_by="negative-test-reviewer",
            reviewed_at="2026-08-24T12:00:00Z",
            reason="negative-test wrong bound qualification",
            store=store,
        )


def test_generation_reload_replays_component_authority(tmp_path: Path) -> None:
    store = _store(tmp_path)
    fixture = synthetic_production_planning_bundle(store=store)
    authority = synthetic_production_champion_authority(store=store, fixture=fixture)

    replayed = load_production_champion_generation(
        authority.generation.artifact_id,
        as_of="2026-08-24T12:00:00Z",
        store=store,
    )

    assert replayed.generation.generation_id == authority.generation.generation.generation_id
