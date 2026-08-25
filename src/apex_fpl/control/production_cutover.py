"""Explicit proof-derived V2 production publication for Slice 13."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterable, Protocol

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.release_registry import ReleaseKey, ReleaseRecord, ReleaseStatus
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.ids import BundleId, GlobalWorldId, ReleaseId
from apex_fpl.core.production import (
    MANDATORY_PRODUCTION_PROOF_IDS,
    ProductionBackendQualification,
    ProductionCutoverReport,
    ProductionCutoverStatus,
)
from apex_fpl.core.proofs import (
    AssuranceCase,
    AssuranceClaim,
    ProofClass,
    ProofObligation,
    ProofStatus,
    ReleasePolicy,
)


class ProductionReleaseRegistry(Protocol):
    """Durable shared production registry port required by cutover."""

    def append(self, record: ReleaseRecord) -> ReleaseRecord: ...

    def read_release(self, release_id: str) -> ReleaseRecord: ...

    def current_release_id(self, key: ReleaseKey) -> str | None: ...

    def compare_and_swap_current(
        self,
        key: ReleaseKey,
        *,
        expected_release_id: str | None,
        new_release_id: str,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ProductionCutoverOutcome:
    report: ProductionCutoverReport
    report_artifact_id: str
    release_record: ReleaseRecord


def _verify_artifact(store: ArtifactStore, artifact_id: str, *, label: str) -> str:
    value = str(artifact_id).strip()
    if not value:
        raise ValueError(f"{label} artifact ID is required")
    if not store.verify(value):
        raise ValueError(f"{label} artifact missing/corrupt: {value}")
    return value


def _claim_artifacts(case: AssuranceCase, store: ArtifactStore) -> tuple[str, ...]:
    artifact_ids = tuple(
        sorted({artifact for claim in case.claims for artifact in claim.artifact_ids})
    )
    for artifact_id in artifact_ids:
        _verify_artifact(store, artifact_id, label="production assurance claim")
    return artifact_ids


def _validate_proof_surface(obligations: tuple[ProofObligation, ...]) -> None:
    proof_ids = [item.proof_id for item in obligations]
    if len(proof_ids) != len(set(proof_ids)):
        raise ValueError("production proof-obligation set contains duplicate proof_id")
    registry = {item.proof_id: item for item in obligations}
    missing = sorted(MANDATORY_PRODUCTION_PROOF_IDS - set(registry))
    if missing:
        raise ValueError(f"production proof surface is incomplete: {missing}")
    downgraded = sorted(
        proof_id
        for proof_id in MANDATORY_PRODUCTION_PROOF_IDS
        if registry[proof_id].release_policy is not ReleasePolicy.REQUIRED
    )
    if downgraded:
        raise ValueError(f"mandatory production proofs are not REQUIRED: {downgraded}")


def _seal_release_policy(
    case: AssuranceCase,
    obligations: tuple[ProofObligation, ...],
    *,
    store: ArtifactStore,
) -> tuple[str, str]:
    ordered = tuple(sorted(obligations, key=lambda item: item.proof_id))
    case_ref = store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": "apex-production-assurance-case-snapshot",
                "schema_version": 1,
                "assurance_case_id": case.case_id,
                "assurance_case": case.semantic_payload(),
            }
        ),
        media_type="application/json",
        schema_name="apex-production-assurance-case-snapshot",
        schema_version="1",
    )
    proof_ref = store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": "apex-production-proof-obligation-snapshot",
                "schema_version": 1,
                "mandatory_production_proof_ids": sorted(MANDATORY_PRODUCTION_PROOF_IDS),
                "obligations": [item.semantic_payload() for item in ordered],
            }
        ),
        media_type="application/json",
        schema_name="apex-production-proof-obligation-snapshot",
        schema_version="1",
    )
    return case_ref.artifact_id, proof_ref.artifact_id


def _seal_backend_qualification(
    qualification: ProductionBackendQualification,
    *,
    store: ArtifactStore,
) -> str:
    ref = store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": "apex-stored-production-backend-qualification",
                "schema_version": 1,
                "qualification_id": qualification.qualification_id,
                "payload": qualification.semantic_payload(),
            }
        ),
        media_type="application/json",
        schema_name="apex-stored-production-backend-qualification",
        schema_version="1",
    )
    return ref.artifact_id


def _release_payload(record: ReleaseRecord) -> dict[str, object]:
    if record.release_id is None:
        raise ValueError("production ReleaseRecord must have release_id before sealing")
    return {
        **record.content_payload(),
        "release_id": record.release_id,
    }


def _seal_release_record(record: ReleaseRecord, *, store: ArtifactStore) -> str:
    ref = store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": "apex-stored-production-release-record",
                "schema_version": 1,
                "release_id": record.release_id,
                "payload": _release_payload(record),
            }
        ),
        media_type="application/json",
        schema_name="apex-stored-production-release-record",
        schema_version="1",
    )
    return ref.artifact_id


def execute_production_cutover(
    *,
    season: str,
    entry: int,
    gameweek: int,
    bundle_id: BundleId | None,
    world_id: GlobalWorldId | None,
    runtime_digest: str,
    created_at: str,
    valid_until: str | None,
    artifact_manifest_id: str,
    assurance_case: AssuranceCase,
    obligations: Iterable[ProofObligation],
    backend_qualification: ProductionBackendQualification,
    artifact_store: ArtifactStore,
    production_registry: ProductionReleaseRegistry,
) -> ProductionCutoverOutcome:
    """Attempt the one explicit V2 production cutover.

    No readiness or safety boolean is accepted. They are derived only after a complete
    ReleaseCertificate PASS, qualified production control-plane evidence and successful
    stale-writer-safe CAS of the exact immutable PUBLISHED ReleaseRecord.
    """

    season = str(season).strip()
    runtime_digest = str(runtime_digest).strip()
    created_at = str(created_at).strip()
    if not season:
        raise ValueError("production season is required")
    if isinstance(entry, bool) or not isinstance(entry, int) or entry <= 0:
        raise ValueError("production entry must be positive integer")
    if isinstance(gameweek, bool) or not isinstance(gameweek, int) or gameweek <= 0:
        raise ValueError("production gameweek must be positive integer")
    if not runtime_digest or not created_at:
        raise ValueError("production runtime_digest and created_at are required")

    obligations_tuple = tuple(sorted(tuple(obligations), key=lambda item: item.proof_id))
    _validate_proof_surface(obligations_tuple)
    manifest_id = _verify_artifact(
        artifact_store,
        artifact_manifest_id,
        label="production artifact manifest",
    )
    claim_artifacts = _claim_artifacts(assurance_case, artifact_store)
    backend_artifacts = (
        _verify_artifact(
            artifact_store,
            backend_qualification.artifact_store_qualification_artifact_id,
            label="production artifact-store qualification",
        ),
        _verify_artifact(
            artifact_store,
            backend_qualification.release_registry_qualification_artifact_id,
            label="production release-registry qualification",
        ),
    )
    case_artifact_id, proof_artifact_id = _seal_release_policy(
        assurance_case,
        obligations_tuple,
        store=artifact_store,
    )
    backend_snapshot_id = _seal_backend_qualification(
        backend_qualification,
        store=artifact_store,
    )
    certificate = assurance_case.derive_release_certificate(obligations_tuple)

    scope = f"{season}:{entry}:{gameweek}:production"
    blockers: list[str] = []
    if assurance_case.release_scope != scope:
        blockers.append(
            f"AssuranceCase release_scope mismatch: expected {scope!r}, "
            f"found {assurance_case.release_scope!r}"
        )
    if backend_qualification.qualification_scope != scope:
        blockers.append(
            f"production backend qualification scope mismatch: expected {scope!r}, "
            f"found {backend_qualification.qualification_scope!r}"
        )
    if not backend_qualification.qualified:
        blockers.append("production ArtifactStore/ReleaseRegistry control plane is not qualified")
    if bundle_id is None:
        blockers.append("production bundle identity is missing")
    if world_id is None:
        blockers.append("production GlobalWorld identity is missing")

    publishable = certificate.eligible and not blockers
    key = ReleaseKey(season, entry, gameweek)
    pointer_before = production_registry.current_release_id(key)

    record = ReleaseRecord(
        season=season,
        entry=entry,
        gameweek=gameweek,
        bundle_id=None if bundle_id is None else str(bundle_id),
        world_id=None if world_id is None else str(world_id),
        runtime_digest=runtime_digest,
        created_at=created_at,
        valid_until=valid_until,
        status=ReleaseStatus.PUBLISHED if publishable else ReleaseStatus.WITHHELD,
        ready_to_act=publishable,
        safe_to_act=publishable,
        artifact_manifest_id=manifest_id,
    ).with_release_id()
    if record.release_id is None:  # pragma: no cover - with_release_id always assigns
        raise RuntimeError("production ReleaseRecord identity was not assigned")
    release_record_artifact_id = _seal_release_record(record, store=artifact_store)

    if publishable:
        appended = production_registry.append(record)
        if appended.release_id != record.release_id:
            raise ValueError("production registry changed immutable ReleaseRecord identity")
        replayed_record = production_registry.read_release(record.release_id)
        if replayed_record != record:
            raise ValueError("production registry ReleaseRecord replay mismatch before publication")
        production_registry.compare_and_swap_current(
            key,
            expected_release_id=pointer_before,
            new_release_id=record.release_id,
        )
        pointer_after = production_registry.current_release_id(key)
        if pointer_after != record.release_id:
            raise ValueError("production CAS completed without exact current release identity")
        status = ProductionCutoverStatus.PUBLISHED
    else:
        pointer_after = production_registry.current_release_id(key)
        if pointer_after != pointer_before:
            raise ValueError("withheld production attempt observed concurrent pointer movement")
        status = ProductionCutoverStatus.WITHHELD

    sources = tuple(
        sorted(
            {
                manifest_id,
                case_artifact_id,
                proof_artifact_id,
                backend_snapshot_id,
                release_record_artifact_id,
                *backend_artifacts,
                *claim_artifacts,
            }
        )
    )
    report = ProductionCutoverReport(
        season=season,
        entry=entry,
        gameweek=gameweek,
        bundle_id=bundle_id,
        world_id=world_id,
        attempt_release_id=ReleaseId(record.release_id),
        release_record_artifact_id=release_record_artifact_id,
        assurance_case_id=certificate.assurance_case_id,
        assurance_case_artifact_id=case_artifact_id,
        proof_obligations_artifact_id=proof_artifact_id,
        release_certificate_status=certificate.status,
        release_certificate_blockers=certificate.blockers,
        cutover_blockers=tuple(blockers),
        backend_qualification_id=backend_qualification.qualification_id,
        backend_qualification_snapshot_artifact_id=backend_snapshot_id,
        backend_qualification_artifact_ids=backend_artifacts,
        production_pointer_before=pointer_before,
        production_pointer_after=pointer_after,
        artifact_manifest_id=manifest_id,
        source_artifact_ids=sources,
        status=status,
    )
    ref = artifact_store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": "apex-stored-production-cutover-report",
                "schema_version": 1,
                "report_id": report.report_id,
                "payload": report.semantic_payload(),
            }
        ),
        media_type="application/json",
        schema_name="apex-stored-production-cutover-report",
        schema_version="1",
    )
    return ProductionCutoverOutcome(report, ref.artifact_id, record)


def _string_tuple(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be string array")
    return tuple(value)


def _load_json_object(
    artifact_id: str,
    *,
    artifact_store: ArtifactStore,
    schema_name: str,
) -> dict[str, object]:
    try:
        raw = json.loads(artifact_store.read_bytes(artifact_id).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{schema_name} artifact is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{schema_name} artifact must be JSON object")
    if raw.get("schema_name") != schema_name or raw.get("schema_version") != 1:
        raise ValueError(f"unsupported {schema_name} schema")
    return raw


def _replay_assurance_case(artifact_id: str, *, artifact_store: ArtifactStore) -> AssuranceCase:
    raw = _load_json_object(
        artifact_id,
        artifact_store=artifact_store,
        schema_name="apex-production-assurance-case-snapshot",
    )
    payload = raw.get("assurance_case")
    declared = raw.get("assurance_case_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("production AssuranceCase snapshot payload/identity is invalid")
    claim_rows = payload.get("claims")
    if not isinstance(claim_rows, list) or any(not isinstance(row, dict) for row in claim_rows):
        raise ValueError("production AssuranceCase claims must be object array")
    claims: list[AssuranceClaim] = []
    for row in claim_rows:
        reason = row.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise ValueError("production AssuranceClaim reason must be string or null")
        claims.append(
            AssuranceClaim(
                proof_id=str(row.get("proof_id") or ""),
                status=ProofStatus(str(row.get("status") or "")),
                evidence_ids=_string_tuple(row.get("evidence_ids"), label="evidence_ids"),
                test_ids=_string_tuple(row.get("test_ids"), label="test_ids"),
                artifact_ids=_string_tuple(row.get("artifact_ids"), label="artifact_ids"),
                reason=reason,
            )
        )
    case = AssuranceCase(
        release_scope=str(payload.get("release_scope") or ""),
        claims=tuple(claims),
    )
    if case.case_id != declared:
        raise ValueError("production AssuranceCase snapshot semantic identity mismatch")
    return case


def _replay_obligations(
    artifact_id: str,
    *,
    artifact_store: ArtifactStore,
) -> tuple[ProofObligation, ...]:
    raw = _load_json_object(
        artifact_id,
        artifact_store=artifact_store,
        schema_name="apex-production-proof-obligation-snapshot",
    )
    mandatory = raw.get("mandatory_production_proof_ids")
    if not isinstance(mandatory, list) or any(not isinstance(item, str) for item in mandatory):
        raise ValueError("production proof snapshot mandatory IDs must be string array")
    if set(mandatory) != set(MANDATORY_PRODUCTION_PROOF_IDS):
        raise ValueError("production proof snapshot constitutional surface drifted")
    rows = raw.get("obligations")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("production proof snapshot obligations must be object array")
    obligations = tuple(
        ProofObligation(
            proof_id=str(row.get("proof_id") or ""),
            claim=str(row.get("claim") or ""),
            proof_class=ProofClass(str(row.get("proof_class") or "")),
            scope=str(row.get("scope") or ""),
            required_evidence=_string_tuple(row.get("required_evidence"), label="required_evidence"),
            required_tests=_string_tuple(row.get("required_tests"), label="required_tests"),
            failure_consequence=str(row.get("failure_consequence") or ""),
            release_policy=ReleasePolicy(str(row.get("release_policy") or "")),
            owner=str(row.get("owner") or ""),
        )
        for row in rows
    )
    ordered = tuple(sorted(obligations, key=lambda item: item.proof_id))
    _validate_proof_surface(ordered)
    return ordered


def _replay_backend_qualification(
    artifact_id: str,
    *,
    artifact_store: ArtifactStore,
) -> ProductionBackendQualification:
    raw = _load_json_object(
        artifact_id,
        artifact_store=artifact_store,
        schema_name="apex-stored-production-backend-qualification",
    )
    payload = raw.get("payload")
    declared = raw.get("qualification_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("production backend qualification payload/identity is invalid")
    bool_fields = (
        "durable_shared_artifact_store",
        "durable_shared_release_registry",
        "atomic_compare_and_swap",
        "immutable_release_history",
    )
    if any(not isinstance(payload.get(name), bool) for name in bool_fields):
        raise ValueError("production backend qualification booleans must be typed")
    qualification = ProductionBackendQualification(
        artifact_store_qualification_artifact_id=str(
            payload.get("artifact_store_qualification_artifact_id") or ""
        ),
        release_registry_qualification_artifact_id=str(
            payload.get("release_registry_qualification_artifact_id") or ""
        ),
        durable_shared_artifact_store=payload["durable_shared_artifact_store"],
        durable_shared_release_registry=payload["durable_shared_release_registry"],
        atomic_compare_and_swap=payload["atomic_compare_and_swap"],
        immutable_release_history=payload["immutable_release_history"],
        qualification_scope=str(payload.get("qualification_scope") or ""),
        schema_version=int(payload.get("schema_version") or 0),
    )
    if qualification.qualification_id != declared:
        raise ValueError("production backend qualification semantic identity mismatch")
    return qualification


def _replay_release_record(artifact_id: str, *, artifact_store: ArtifactStore) -> ReleaseRecord:
    raw = _load_json_object(
        artifact_id,
        artifact_store=artifact_store,
        schema_name="apex-stored-production-release-record",
    )
    payload = raw.get("payload")
    declared = raw.get("release_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("production ReleaseRecord payload/identity is invalid")
    entry = payload.get("entry")
    gameweek = payload.get("gameweek")
    ready = payload.get("ready_to_act")
    safe = payload.get("safe_to_act")
    if isinstance(entry, bool) or not isinstance(entry, int):
        raise ValueError("production replay ReleaseRecord entry must be integer")
    if gameweek is not None and (isinstance(gameweek, bool) or not isinstance(gameweek, int)):
        raise ValueError("production replay ReleaseRecord gameweek must be integer or null")
    if not isinstance(ready, bool) or not isinstance(safe, bool):
        raise ValueError("production replay ReleaseRecord readiness must be typed booleans")
    record = ReleaseRecord(
        season=str(payload.get("season") or ""),
        entry=entry,
        gameweek=gameweek,
        bundle_id=None if payload.get("bundle_id") is None else str(payload.get("bundle_id")),
        world_id=None if payload.get("world_id") is None else str(payload.get("world_id")),
        runtime_digest=str(payload.get("runtime_digest") or ""),
        created_at=str(payload.get("created_at") or ""),
        valid_until=None if payload.get("valid_until") is None else str(payload.get("valid_until")),
        status=ReleaseStatus(str(payload.get("status") or "")),
        ready_to_act=ready,
        safe_to_act=safe,
        artifact_manifest_id=str(payload.get("artifact_manifest_id") or ""),
        superseded_by=None if payload.get("superseded_by") is None else str(payload.get("superseded_by")),
        release_id=declared,
    )
    if record.with_release_id().release_id != declared or payload.get("release_id") != declared:
        raise ValueError("production ReleaseRecord semantic identity mismatch")
    return record


def load_production_cutover_report(
    artifact_id: str,
    *,
    artifact_store: ArtifactStore,
) -> ProductionCutoverReport:
    """Replay a production cutover report and re-derive all pre-publication proof state."""

    raw = _load_json_object(
        artifact_id,
        artifact_store=artifact_store,
        schema_name="apex-stored-production-cutover-report",
    )
    payload = raw.get("payload")
    report_id = raw.get("report_id")
    if not isinstance(payload, dict) or not isinstance(report_id, str):
        raise ValueError("stored production cutover report payload/identity is invalid")

    report = ProductionCutoverReport(
        season=str(payload.get("season") or ""),
        entry=int(payload.get("entry") or 0),
        gameweek=int(payload.get("gameweek") or 0),
        bundle_id=None if payload.get("bundle_id") is None else BundleId(str(payload.get("bundle_id"))),
        world_id=None if payload.get("world_id") is None else GlobalWorldId(str(payload.get("world_id"))),
        attempt_release_id=ReleaseId(str(payload.get("attempt_release_id") or "")),
        release_record_artifact_id=str(payload.get("release_record_artifact_id") or ""),
        assurance_case_id=str(payload.get("assurance_case_id") or ""),
        assurance_case_artifact_id=str(payload.get("assurance_case_artifact_id") or ""),
        proof_obligations_artifact_id=str(payload.get("proof_obligations_artifact_id") or ""),
        release_certificate_status=str(payload.get("release_certificate_status") or ""),
        release_certificate_blockers=_string_tuple(
            payload.get("release_certificate_blockers"), label="release_certificate_blockers"
        ),
        cutover_blockers=_string_tuple(payload.get("cutover_blockers"), label="cutover_blockers"),
        backend_qualification_id=str(payload.get("backend_qualification_id") or ""),
        backend_qualification_snapshot_artifact_id=str(
            payload.get("backend_qualification_snapshot_artifact_id") or ""
        ),
        backend_qualification_artifact_ids=_string_tuple(
            payload.get("backend_qualification_artifact_ids"),
            label="backend_qualification_artifact_ids",
        ),
        production_pointer_before=(
            None
            if payload.get("production_pointer_before") is None
            else str(payload.get("production_pointer_before"))
        ),
        production_pointer_after=(
            None
            if payload.get("production_pointer_after") is None
            else str(payload.get("production_pointer_after"))
        ),
        artifact_manifest_id=str(payload.get("artifact_manifest_id") or ""),
        source_artifact_ids=_string_tuple(
            payload.get("source_artifact_ids"), label="source_artifact_ids"
        ),
        status=ProductionCutoverStatus(str(payload.get("status") or "")),
        schema_version=int(payload.get("schema_version") or 0),
    )
    if report.report_id != report_id:
        raise ValueError("production cutover report semantic identity mismatch")

    for source_id in report.source_artifact_ids:
        _verify_artifact(artifact_store, source_id, label="production replay source")
    case = _replay_assurance_case(
        report.assurance_case_artifact_id,
        artifact_store=artifact_store,
    )
    obligations = _replay_obligations(
        report.proof_obligations_artifact_id,
        artifact_store=artifact_store,
    )
    certificate = case.derive_release_certificate(obligations)
    if certificate.assurance_case_id != report.assurance_case_id:
        raise ValueError("replayed production AssuranceCase identity does not match report")
    if certificate.status != report.release_certificate_status:
        raise ValueError("replayed production ReleaseCertificate status does not match report")
    if certificate.blockers != report.release_certificate_blockers:
        raise ValueError("replayed production ReleaseCertificate blockers do not match report")

    qualification = _replay_backend_qualification(
        report.backend_qualification_snapshot_artifact_id,
        artifact_store=artifact_store,
    )
    if qualification.qualification_id != report.backend_qualification_id:
        raise ValueError("replayed backend qualification identity does not match report")
    if tuple(
        sorted(
            (
                qualification.artifact_store_qualification_artifact_id,
                qualification.release_registry_qualification_artifact_id,
            )
        )
    ) != tuple(sorted(report.backend_qualification_artifact_ids)):
        raise ValueError("replayed backend qualification evidence does not match report")

    record = _replay_release_record(
        report.release_record_artifact_id,
        artifact_store=artifact_store,
    )
    if record.release_id != str(report.attempt_release_id):
        raise ValueError("replayed production ReleaseRecord identity does not match report")
    expected_published = report.status is ProductionCutoverStatus.PUBLISHED
    if record.status is not (
        ReleaseStatus.PUBLISHED if expected_published else ReleaseStatus.WITHHELD
    ):
        raise ValueError("replayed production ReleaseRecord status does not match report")
    if record.ready_to_act is not expected_published or record.safe_to_act is not expected_published:
        raise ValueError("replayed production ReleaseRecord readiness does not match cutover status")
    if record.artifact_manifest_id != report.artifact_manifest_id:
        raise ValueError("replayed production ReleaseRecord manifest does not match report")
    return report
