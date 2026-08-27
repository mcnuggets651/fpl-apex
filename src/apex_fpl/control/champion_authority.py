"""Administrative champion admission and runtime replay for Apex V2.

This module deliberately separates *qualification* from *selection authority*. Runtime
publication code may call only the replay/verification functions; admission and generation
creation are administrative operations and are guarded by architecture tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Mapping

from apex_fpl.control.artifact_store import ArtifactIntegrityError, ArtifactStore
from apex_fpl.control.empirical_qualification_admission import (
    SCENARIO_GENERATOR_QUALIFICATION_ID,
    SCENARIO_POLICY_QUALIFICATION_ID,
    verify_typed_empirical_qualification,
)
from apex_fpl.control.learning_promotion_replay import verify_forecast_registry_champion
from apex_fpl.control.production_planning_bundle import VerifiedProductionPlanningBundle
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.champion_authority import (
    ChampionAdmissionCertificate,
    ChampionRole,
    ProductionChampionGeneration,
)


_DECISION_POLICY_QUALIFICATION_ID = "PO-DECISION-POLICY-QUALIFICATION-001"
_ROLE_CONTRACT = {
    ChampionRole.DECISION_POLICY: (
        "apex.decision-policy",
        _DECISION_POLICY_QUALIFICATION_ID,
    ),
    ChampionRole.SCENARIO_GENERATOR: (
        "apex.scenario-generator",
        SCENARIO_GENERATOR_QUALIFICATION_ID,
    ),
    ChampionRole.SCENARIO_POLICY: (
        "apex.scenario-policy",
        SCENARIO_POLICY_QUALIFICATION_ID,
    ),
}


@dataclass(frozen=True, slots=True)
class StoredChampionAdmission:
    certificate: ChampionAdmissionCertificate
    artifact_id: str


@dataclass(frozen=True, slots=True)
class StoredChampionGeneration:
    generation: ProductionChampionGeneration
    artifact_id: str


def _instant(value: str, *, label: str) -> datetime:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def _read_json(artifact_id: str, *, store: ArtifactStore, label: str) -> dict[str, object]:
    try:
        content = store.read_bytes(artifact_id)
    except (FileNotFoundError, ArtifactIntegrityError) as exc:
        raise ValueError(f"{label} failed integrity verification") from exc
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be JSON object")
    return dict(value)


def _verify_artifact(artifact_id: str, *, store: ArtifactStore, label: str) -> str:
    value = str(artifact_id).strip()
    if not value or not store.verify(value):
        raise ValueError(f"{label} is missing/corrupt")
    return value


def _candidate_payload(candidate_id: str, *, store: ArtifactStore) -> dict[str, object]:
    payload = _read_json(
        candidate_id,
        store=store,
        label="champion candidate semantic artifact",
    )
    if canonical_sha256(payload) != candidate_id:
        raise ValueError("champion candidate semantic identity mismatch")
    if canonical_json_bytes(payload) != store.read_bytes(candidate_id):
        raise ValueError("champion candidate semantic artifact is not canonical JSON")
    return payload


def _verify_admission_certificate(
    certificate: ChampionAdmissionCertificate,
    *,
    as_of: str,
    store: ArtifactStore,
) -> dict[str, object]:
    if _instant(as_of, label="champion admission replay as_of") < _instant(
        certificate.reviewed_at,
        label="champion admission reviewed_at",
    ):
        raise ValueError("champion admission did not exist at replay as_of")
    _verify_artifact(
        certificate.review_artifact_id,
        store=store,
        label="champion review evidence",
    )
    payload = _candidate_payload(certificate.candidate_id, store=store)
    subject_kind, proof_id = _ROLE_CONTRACT[certificate.role]
    verify_typed_empirical_qualification(
        qualification_artifact_id=certificate.qualification_artifact_id,
        subject_payload=payload,
        subject_kind=subject_kind,
        proof_id=proof_id,
        season=certificate.season,
        as_of=as_of,
        store=store,
    )
    return payload


def issue_champion_admission(
    *,
    role: ChampionRole,
    season: str,
    candidate_id: str,
    subject_payload: Mapping[str, object],
    qualification_artifact_id: str,
    review_artifact_id: str,
    reviewed_by: str,
    reviewed_at: str,
    reason: str,
    store: ArtifactStore,
) -> StoredChampionAdmission:
    """Administratively admit one empirically-qualified non-model champion candidate."""

    candidate_payload = dict(subject_payload)
    if canonical_sha256(candidate_payload) != str(candidate_id):
        raise ValueError("champion admission candidate_id does not match candidate semantics")
    candidate_ref = store.put_bytes(
        canonical_json_bytes(candidate_payload),
        media_type="application/json",
        schema_name="apex-champion-candidate-semantics",
        schema_version="1",
    )
    if candidate_ref.artifact_id != str(candidate_id):
        raise ValueError("champion candidate semantic artifact identity mismatch")
    certificate = ChampionAdmissionCertificate(
        role=role,
        season=season,
        candidate_id=str(candidate_id),
        qualification_artifact_id=qualification_artifact_id,
        review_artifact_id=review_artifact_id,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
        reason=reason,
    )
    _verify_admission_certificate(certificate, as_of=reviewed_at, store=store)
    envelope = {
        "schema_name": "apex-stored-champion-admission",
        "schema_version": 1,
        "admission_id": certificate.admission_id,
        "payload": certificate.semantic_payload(),
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name="apex-stored-champion-admission",
        schema_version="1",
    )
    return StoredChampionAdmission(certificate, ref.artifact_id)


def load_champion_admission(
    artifact_id: str,
    *,
    as_of: str,
    store: ArtifactStore,
) -> StoredChampionAdmission:
    raw = _read_json(artifact_id, store=store, label="champion admission")
    if (
        raw.get("schema_name") != "apex-stored-champion-admission"
        or raw.get("schema_version") != 1
    ):
        raise ValueError("unsupported champion admission schema")
    payload = raw.get("payload")
    declared = raw.get("admission_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("champion admission payload/identity is invalid")
    certificate = ChampionAdmissionCertificate(
        role=ChampionRole(str(payload.get("role") or "")),
        season=str(payload.get("season") or ""),
        candidate_id=str(payload.get("candidate_id") or ""),
        qualification_artifact_id=str(payload.get("qualification_artifact_id") or ""),
        review_artifact_id=str(payload.get("review_artifact_id") or ""),
        reviewed_by=str(payload.get("reviewed_by") or ""),
        reviewed_at=str(payload.get("reviewed_at") or ""),
        reason=str(payload.get("reason") or ""),
        schema_version=int(payload.get("schema_version") or 0),
    )
    if certificate.admission_id != declared:
        raise ValueError("champion admission semantic identity mismatch")
    _verify_admission_certificate(certificate, as_of=as_of, store=store)
    return StoredChampionAdmission(certificate, artifact_id)


def _forecast_champion(
    registry_generation_artifact_id: str,
    *,
    season: str,
    as_of: str,
    store: ArtifactStore,
) -> str:
    evidence = verify_forecast_registry_champion(
        registry_generation_artifact_id,
        season=season,
        as_of=as_of,
        store=store,
    )
    return evidence.champion_model_id


def _load_generation_contract(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> ProductionChampionGeneration:
    raw = _read_json(artifact_id, store=store, label="production champion generation")
    if (
        raw.get("schema_name") != "apex-stored-production-champion-generation"
        or raw.get("schema_version") != 1
    ):
        raise ValueError("unsupported stored production champion generation schema")
    payload = raw.get("payload")
    declared = raw.get("generation_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("production champion generation payload/identity is invalid")
    generation_raw = payload.get("generation")
    schema_raw = payload.get("schema_version")
    if isinstance(generation_raw, bool) or not isinstance(generation_raw, int):
        raise ValueError("production champion generation number must be integer")
    if isinstance(schema_raw, bool) or not isinstance(schema_raw, int):
        raise ValueError("production champion generation schema_version must be integer")
    parent_raw = payload.get("parent_generation_artifact_id")
    if parent_raw is not None and not isinstance(parent_raw, str):
        raise ValueError("production champion parent artifact must be string or null")
    generation = ProductionChampionGeneration(
        season=str(payload.get("season") or ""),
        generation=generation_raw,
        parent_generation_artifact_id=parent_raw,
        forecast_registry_generation_artifact_id=str(
            payload.get("forecast_registry_generation_artifact_id") or ""
        ),
        forecast_model_id=str(payload.get("forecast_model_id") or ""),
        decision_policy_admission_artifact_id=str(
            payload.get("decision_policy_admission_artifact_id") or ""
        ),
        decision_policy_id=str(payload.get("decision_policy_id") or ""),
        scenario_generator_admission_artifact_id=str(
            payload.get("scenario_generator_admission_artifact_id") or ""
        ),
        scenario_generator_id=str(payload.get("scenario_generator_id") or ""),
        scenario_policy_admission_artifact_id=str(
            payload.get("scenario_policy_admission_artifact_id") or ""
        ),
        scenario_policy_id=str(payload.get("scenario_policy_id") or ""),
        change_control_artifact_id=str(
            payload.get("change_control_artifact_id") or ""
        ),
        authorized_by=str(payload.get("authorized_by") or ""),
        authorized_at=str(payload.get("authorized_at") or ""),
        reason=str(payload.get("reason") or ""),
        schema_version=schema_raw,
    )
    if generation.generation_id != declared:
        raise ValueError("production champion generation semantic identity mismatch")
    return generation


def load_production_champion_generation(
    artifact_id: str,
    *,
    as_of: str,
    store: ArtifactStore,
) -> StoredChampionGeneration:
    generation = _load_generation_contract(artifact_id, store=store)
    replay_at = _instant(as_of, label="champion generation replay as_of")
    authorized_at = _instant(
        generation.authorized_at,
        label="champion generation authorized_at",
    )
    if replay_at < authorized_at:
        raise ValueError("production champion generation did not exist at replay as_of")
    _verify_artifact(
        generation.change_control_artifact_id,
        store=store,
        label="champion generation change-control evidence",
    )
    if generation.parent_generation_artifact_id is not None:
        parent = load_production_champion_generation(
            generation.parent_generation_artifact_id,
            as_of=generation.authorized_at,
            store=store,
        ).generation
        if (
            parent.season != generation.season
            or parent.generation + 1 != generation.generation
        ):
            raise ValueError("production champion parent lineage is not contiguous")
    forecast_champion = _forecast_champion(
        generation.forecast_registry_generation_artifact_id,
        season=generation.season,
        as_of=generation.authorized_at,
        store=store,
    )
    if forecast_champion != generation.forecast_model_id:
        raise ValueError("production champion generation forecast authority mismatch")
    role_bindings = (
        (
            ChampionRole.DECISION_POLICY,
            generation.decision_policy_admission_artifact_id,
            generation.decision_policy_id,
        ),
        (
            ChampionRole.SCENARIO_GENERATOR,
            generation.scenario_generator_admission_artifact_id,
            generation.scenario_generator_id,
        ),
        (
            ChampionRole.SCENARIO_POLICY,
            generation.scenario_policy_admission_artifact_id,
            generation.scenario_policy_id,
        ),
    )
    for role, admission_artifact_id, expected_candidate_id in role_bindings:
        admitted_at_authorization = load_champion_admission(
            admission_artifact_id,
            as_of=generation.authorized_at,
            store=store,
        ).certificate
        if replay_at > authorized_at:
            admission = load_champion_admission(
                admission_artifact_id,
                as_of=as_of,
                store=store,
            ).certificate
        else:
            admission = admitted_at_authorization
        if admission.role is not role:
            raise ValueError("production champion admission role mismatch")
        if admission.season != generation.season:
            raise ValueError("production champion admission season mismatch")
        if admission.candidate_id != expected_candidate_id:
            raise ValueError("production champion admission candidate mismatch")
    return StoredChampionGeneration(generation, artifact_id)


def create_production_champion_generation(
    *,
    season: str,
    forecast_registry_generation_artifact_id: str,
    decision_policy_admission_artifact_id: str,
    scenario_generator_admission_artifact_id: str,
    scenario_policy_admission_artifact_id: str,
    change_control_artifact_id: str,
    authorized_by: str,
    authorized_at: str,
    reason: str,
    current_generation_artifact_id: str | None,
    expected_parent_generation_id: str | None,
    store: ArtifactStore,
) -> StoredChampionGeneration:
    """Administratively create a parent-linked champion generation.

    ``expected_parent_generation_id`` is the stale-writer guard: when a supplied current
    generation exists its semantic identity must exactly equal the caller's expected parent.
    """

    _instant(authorized_at, label="champion generation authorized_at")
    if current_generation_artifact_id is None:
        if expected_parent_generation_id is not None:
            raise ValueError("initial champion generation cannot declare expected parent")
        generation_number = 1
        parent_artifact_id = None
    else:
        current = load_production_champion_generation(
            current_generation_artifact_id,
            as_of=authorized_at,
            store=store,
        ).generation
        if expected_parent_generation_id != current.generation_id:
            raise ValueError(
                "stale champion-generation writer: expected parent does not match current"
            )
        if current.season != season:
            raise ValueError("champion generation cannot cross season boundary")
        generation_number = current.generation + 1
        parent_artifact_id = current_generation_artifact_id

    forecast_model_id = _forecast_champion(
        forecast_registry_generation_artifact_id,
        season=season,
        as_of=authorized_at,
        store=store,
    )
    admissions = {
        role: load_champion_admission(
            artifact_id,
            as_of=authorized_at,
            store=store,
        ).certificate
        for role, artifact_id in (
            (ChampionRole.DECISION_POLICY, decision_policy_admission_artifact_id),
            (ChampionRole.SCENARIO_GENERATOR, scenario_generator_admission_artifact_id),
            (ChampionRole.SCENARIO_POLICY, scenario_policy_admission_artifact_id),
        )
    }
    for role, admission in admissions.items():
        if admission.role is not role or admission.season != season:
            raise ValueError("champion generation admission role/season mismatch")
    generation = ProductionChampionGeneration(
        season=season,
        generation=generation_number,
        parent_generation_artifact_id=parent_artifact_id,
        forecast_registry_generation_artifact_id=(
            forecast_registry_generation_artifact_id
        ),
        forecast_model_id=forecast_model_id,
        decision_policy_admission_artifact_id=(
            decision_policy_admission_artifact_id
        ),
        decision_policy_id=admissions[ChampionRole.DECISION_POLICY].candidate_id,
        scenario_generator_admission_artifact_id=(
            scenario_generator_admission_artifact_id
        ),
        scenario_generator_id=admissions[ChampionRole.SCENARIO_GENERATOR].candidate_id,
        scenario_policy_admission_artifact_id=scenario_policy_admission_artifact_id,
        scenario_policy_id=admissions[ChampionRole.SCENARIO_POLICY].candidate_id,
        change_control_artifact_id=change_control_artifact_id,
        authorized_by=authorized_by,
        authorized_at=authorized_at,
        reason=reason,
    )
    _verify_artifact(
        generation.change_control_artifact_id,
        store=store,
        label="champion generation change-control evidence",
    )
    envelope = {
        "schema_name": "apex-stored-production-champion-generation",
        "schema_version": 1,
        "generation_id": generation.generation_id,
        "payload": generation.semantic_payload(),
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name="apex-stored-production-champion-generation",
        schema_version="1",
    )
    stored = StoredChampionGeneration(generation, ref.artifact_id)
    load_production_champion_generation(
        ref.artifact_id,
        as_of=authorized_at,
        store=store,
    )
    return stored


def verify_bundle_champion_authority(
    champion_generation_artifact_id: str,
    *,
    verified_bundle: VerifiedProductionPlanningBundle,
    as_of: str,
    store: ArtifactStore,
) -> StoredChampionGeneration:
    """Independently replay authority and exact-match all four runtime champion IDs."""

    stored = load_production_champion_generation(
        champion_generation_artifact_id,
        as_of=as_of,
        store=store,
    )
    generation = stored.generation
    bundle = verified_bundle.bundle
    if generation.season != bundle.season:
        raise ValueError("production champion generation season does not match bundle")
    expected = {
        "forecast model": str(verified_bundle.forecast_model.model_artifact_id),
        "decision policy": str(verified_bundle.decision_policy.decision_policy_id),
        "scenario generator": str(verified_bundle.scenario_set.scenario_generator_id),
        "scenario policy": str(verified_bundle.robustness_report.scenario_policy_id),
    }
    authorized = {
        "forecast model": generation.forecast_model_id,
        "decision policy": generation.decision_policy_id,
        "scenario generator": generation.scenario_generator_id,
        "scenario policy": generation.scenario_policy_id,
    }
    mismatches = [
        label for label in expected if expected[label] != authorized[label]
    ]
    if mismatches:
        raise ValueError(
            "production bundle uses champion identities not authorized by replayed generation: "
            + ", ".join(sorted(mismatches))
        )
    return stored
