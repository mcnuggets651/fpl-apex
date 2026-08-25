"""Explicit proof-derived V2 production publication for Slice 13."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Iterable, Protocol

from apex_fpl.control.artifact_store import ArtifactIntegrityError, ArtifactStore
from apex_fpl.control.experiment_registry import load_empirical_qualification_certificate
from apex_fpl.control.production_planning_bundle import (
    VerifiedProductionPlanningBundle,
    load_production_planning_bundle,
)
from apex_fpl.control.production_reference_solver_binding import (
    REFERENCE_SOLVER_PARITY_PROOF_ID,
    claim_has_matching_planning_reference_solver_parity,
)
from apex_fpl.control.release_registry import ReleaseKey, ReleaseRecord, ReleaseStatus
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.experiments import qualification_subject_id
from apex_fpl.core.ids import BundleId, GlobalWorldId, ReleaseId
from apex_fpl.core.production import (
    MANDATORY_PRODUCTION_PROOF_IDS,
    ProductionBackendQualification,
    ProductionCutoverReport,
    ProductionCutoverStatus,
    ProductionPublicationAuthorization,
)
from apex_fpl.core.production_proof_contract import (
    EMPIRICAL_PRODUCTION_PROOF_IDS,
    PRODUCTION_EMPIRICAL_SUBJECT_KIND,
    PRODUCTION_PROOF_CLASSES,
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

    backend_id: str

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


@dataclass(frozen=True, slots=True)
class _EmpiricalReleaseBinding:
    subject_id: str
    semantic_evidence_id: str
    qualification_artifact_id: str | None = None


def _verify_artifact(store: ArtifactStore, artifact_id: str, *, label: str) -> str:
    value = str(artifact_id).strip()
    if not value:
        raise ValueError(f"{label} artifact ID is required")
    if not store.verify(value):
        raise ValueError(f"{label} artifact missing/corrupt: {value}")
    return value


def _validate_proof_surface(obligations: tuple[ProofObligation, ...]) -> None:
    if set(PRODUCTION_PROOF_CLASSES) != set(MANDATORY_PRODUCTION_PROOF_IDS):
        raise ValueError("production proof-class contract drifted from mandatory proof surface")
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
    reclassified = sorted(
        proof_id
        for proof_id in MANDATORY_PRODUCTION_PROOF_IDS
        if registry[proof_id].proof_class is not PRODUCTION_PROOF_CLASSES[proof_id]
    )
    if reclassified:
        raise ValueError(f"mandatory production proof class drifted: {reclassified}")


def _backend_id(value: object, *, label: str) -> str:
    backend_id = getattr(value, "backend_id", None)
    if not isinstance(backend_id, str) or not backend_id.strip():
        raise ValueError(f"{label} has no stable production backend identity")
    return backend_id.strip()


def _validate_backend_binding(
    *,
    artifact_store: ArtifactStore,
    production_registry: ProductionReleaseRegistry,
    qualification: ProductionBackendQualification,
) -> None:
    artifact_backend_id = _backend_id(artifact_store, label="production ArtifactStore")
    registry_backend_id = _backend_id(
        production_registry,
        label="production ReleaseRegistry",
    )
    if artifact_backend_id != qualification.artifact_store_backend_id:
        raise ValueError(
            "production ArtifactStore backend identity does not match qualification"
        )
    if registry_backend_id != qualification.release_registry_backend_id:
        raise ValueError(
            "production ReleaseRegistry backend identity does not match qualification"
        )


def _bundle_empirical_bindings(
    verified: VerifiedProductionPlanningBundle | None,
) -> dict[str, _EmpiricalReleaseBinding]:
    if verified is None:
        return {}
    model = verified.forecast_model
    policy = verified.decision_policy
    report = verified.robustness_report
    if model.qualification_artifact_id is None or policy.qualification_artifact_id is None:
        raise ValueError("production bundle direct empirical subjects lack qualification artifacts")
    return {
        "PO-FORECAST-QUALIFICATION-001": _EmpiricalReleaseBinding(
            subject_id=qualification_subject_id(model.semantic_payload()),
            semantic_evidence_id=str(model.model_artifact_id),
            qualification_artifact_id=model.qualification_artifact_id,
        ),
        "PO-DECISION-POLICY-QUALIFICATION-001": _EmpiricalReleaseBinding(
            subject_id=qualification_subject_id(policy.semantic_payload()),
            semantic_evidence_id=str(policy.decision_policy_id),
            qualification_artifact_id=policy.qualification_artifact_id,
        ),
        "PO-SCENARIO-CONVERGENCE-001": _EmpiricalReleaseBinding(
            subject_id=qualification_subject_id(report.semantic_payload()),
            semantic_evidence_id=str(report.robustness_report_id),
        ),
    }


def _verified_bundle_for_release(
    *,
    bundle_id: BundleId | None,
    world_id: GlobalWorldId | None,
    season: str,
    entry: int,
    gameweek: int,
    store: ArtifactStore,
) -> VerifiedProductionPlanningBundle | None:
    if bundle_id is None:
        return None
    verified = load_production_planning_bundle(bundle_id, store=store)
    bundle = verified.bundle
    if bundle.season != season:
        raise ValueError("production bundle season does not match release scope")
    if bundle.entry != entry:
        raise ValueError("production bundle entry does not match release scope")
    if bundle.gameweek != gameweek:
        raise ValueError("production bundle gameweek does not match release scope")
    if world_id is not None and bundle.world_id != world_id:
        raise ValueError("production bundle world does not match release world")
    return verified


def _claim_has_matching_empirical_qualification(
    *,
    claim: AssuranceClaim,
    proof_id: str,
    season: str,
    as_of: str,
    store: ArtifactStore,
    binding: _EmpiricalReleaseBinding | None,
) -> bool:
    evidence_ids = set(claim.evidence_ids)
    expected_kind = PRODUCTION_EMPIRICAL_SUBJECT_KIND[proof_id]
    for artifact_id in claim.artifact_ids:
        if binding is not None and binding.qualification_artifact_id is not None:
            if artifact_id != binding.qualification_artifact_id:
                continue
        try:
            qualification = load_empirical_qualification_certificate(
                artifact_id,
                store=store,
                as_of=as_of,
            )
        except ValueError:
            continue
        if (
            not qualification.supported
            or qualification.proof_id != proof_id
            or qualification.subject_kind != expected_kind
            or qualification.season != season
            or qualification.subject_id not in evidence_ids
            or qualification.experiment_id not in evidence_ids
        ):
            continue
        if binding is not None and (
            qualification.subject_id != binding.subject_id
            or binding.semantic_evidence_id not in evidence_ids
        ):
            continue
        return True
    return False


def _claim_artifacts(
    case: AssuranceCase,
    obligations: tuple[ProofObligation, ...],
    store: ArtifactStore,
    *,
    season: str,
    as_of: str,
    empirical_bindings: dict[str, _EmpiricalReleaseBinding] | None = None,
    verified_bundle: VerifiedProductionPlanningBundle | None = None,
) -> tuple[str, ...]:
    """Verify retained evidence behind every satisfying mandatory proof claim."""

    bindings = empirical_bindings or {}
    registry = {item.proof_id: item for item in obligations}
    claim_map = {claim.proof_id: claim for claim in case.claims}
    for proof_id in sorted(MANDATORY_PRODUCTION_PROOF_IDS):
        claim = claim_map.get(proof_id)
        if claim is None:
            continue
        obligation = registry[proof_id]
        satisfying = (
            claim.status is ProofStatus.PROVEN
            if obligation.proof_class
            in {
                ProofClass.FORMAL_INVARIANT,
                ProofClass.ALGORITHMIC_CERTIFICATE,
                ProofClass.PROVENANCE_ASSERTION,
                ProofClass.DATA_INTEGRITY_ASSERTION,
            }
            else claim.status in {ProofStatus.PROVEN, ProofStatus.SUPPORTED}
        )
        if satisfying and not claim.artifact_ids:
            raise ValueError(
                f"mandatory satisfying production proof lacks immutable artifact evidence: {proof_id}"
            )
        if (
            satisfying
            and proof_id in EMPIRICAL_PRODUCTION_PROOF_IDS
            and not _claim_has_matching_empirical_qualification(
                claim=claim,
                proof_id=proof_id,
                season=season,
                as_of=as_of,
                store=store,
                binding=bindings.get(proof_id),
            )
        ):
            raise ValueError(
                "mandatory empirical production proof lacks matching typed "
                f"qualification evidence: {proof_id}"
            )
        if satisfying and proof_id == REFERENCE_SOLVER_PARITY_PROOF_ID:
            if verified_bundle is None or not claim_has_matching_planning_reference_solver_parity(
                claim,
                verified_bundle=verified_bundle,
                store=store,
            ):
                raise ValueError(
                    "mandatory reference-solver production proof lacks replay-valid "
                    "planning parity and qualified-champion authorization"
                )
    artifact_ids = tuple(
        sorted({artifact for claim in case.claims for artifact in claim.artifact_ids})
    )
    for artifact_id in artifact_ids:
        _verify_artifact(store, artifact_id, label="production assurance claim")
    return artifact_ids


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


def _seal_publication_authorization(
    authorization: ProductionPublicationAuthorization,
    *,
    store: ArtifactStore,
) -> str:
    ref = store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": "apex-stored-production-publication-authorization",
                "schema_version": 1,
                "authorization_id": authorization.authorization_id,
                "payload": authorization.semantic_payload(),
            }
        ),
        media_type="application/json",
        schema_name="apex-stored-production-publication-authorization",
        schema_version="1",
    )
    return ref.artifact_id


def _release_payload(record: ReleaseRecord) -> dict[str, object]:
    if record.release_id is None:
        raise ValueError("production ReleaseRecord must have release_id before sealing")
    return {**record.content_payload(), "release_id": record.release_id}


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


def _parse_timestamp(value: str, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is not valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def _cutover_blockers(
    *,
    season: str,
    entry: int,
    gameweek: int,
    bundle_id: BundleId | None,
    world_id: GlobalWorldId | None,
    created_at: str,
    valid_until: str | None,
    assurance_case: AssuranceCase,
    backend_qualification: ProductionBackendQualification,
) -> tuple[str, ...]:
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

    created: datetime | None = None
    try:
        created = _parse_timestamp(created_at, label="production created_at")
    except ValueError as exc:
        blockers.append(str(exc))
    if valid_until is None:
        blockers.append("production release validity horizon is missing")
    else:
        try:
            valid = _parse_timestamp(valid_until, label="production valid_until")
        except ValueError as exc:
            blockers.append(str(exc))
        else:
            if created is not None and valid <= created:
                blockers.append("production valid_until must be later than created_at")
    return tuple(blockers)


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
    """Attempt the one explicit V2 production cutover."""

    season = str(season).strip()
    runtime_digest = str(runtime_digest).strip()
    created_at = str(created_at).strip()
    valid_until = None if valid_until is None else str(valid_until).strip()
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
    _validate_backend_binding(
        artifact_store=artifact_store,
        production_registry=production_registry,
        qualification=backend_qualification,
    )
    verified_bundle = _verified_bundle_for_release(
        bundle_id=bundle_id,
        world_id=world_id,
        season=season,
        entry=entry,
        gameweek=gameweek,
        store=artifact_store,
    )
    empirical_bindings = _bundle_empirical_bindings(verified_bundle)
    manifest_id = _verify_artifact(
        artifact_store, artifact_manifest_id, label="production artifact manifest"
    )
    claim_artifacts = _claim_artifacts(
        assurance_case,
        obligations_tuple,
        artifact_store,
        season=season,
        as_of=created_at,
        empirical_bindings=empirical_bindings,
        verified_bundle=verified_bundle,
    )
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
        assurance_case, obligations_tuple, store=artifact_store
    )
    backend_snapshot_id = _seal_backend_qualification(
        backend_qualification, store=artifact_store
    )
    certificate = assurance_case.derive_release_certificate(obligations_tuple)
    blockers = _cutover_blockers(
        season=season,
        entry=entry,
        gameweek=gameweek,
        bundle_id=bundle_id,
        world_id=world_id,
        created_at=created_at,
        valid_until=valid_until,
        assurance_case=assurance_case,
        backend_qualification=backend_qualification,
    )
    authorization = ProductionPublicationAuthorization(
        season=season,
        entry=entry,
        gameweek=gameweek,
        bundle_id=bundle_id,
        world_id=world_id,
        runtime_digest=runtime_digest,
        created_at=created_at,
        valid_until=valid_until,
        artifact_manifest_id=manifest_id,
        assurance_case_id=certificate.assurance_case_id,
        assurance_case_artifact_id=case_artifact_id,
        proof_obligations_artifact_id=proof_artifact_id,
        release_certificate_status=certificate.status,
        release_certificate_blockers=certificate.blockers,
        cutover_blockers=blockers,
        backend_qualification_id=backend_qualification.qualification_id,
        backend_qualification_snapshot_artifact_id=backend_snapshot_id,
        backend_qualification_artifact_ids=backend_artifacts,
    )
    authorization_artifact_id = _seal_publication_authorization(
        authorization, store=artifact_store
    )
    publishable = authorization.authorized
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
        publication_authorization_artifact_id=authorization_artifact_id,
    ).with_release_id()
    if record.release_id is None:  # pragma: no cover
        raise RuntimeError("production ReleaseRecord identity was not assigned")
    release_record_artifact_id = _seal_release_record(record, store=artifact_store)

    if publishable:
        appended = production_registry.append(record)
        if appended.release_id != record.release_id:
            raise ValueError("production registry changed immutable ReleaseRecord identity")
        if production_registry.read_release(record.release_id) != record:
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
                authorization_artifact_id,
                release_record_artifact_id,
                *((str(bundle_id),) if bundle_id is not None else ()),
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
        publication_authorization_artifact_id=authorization_artifact_id,
        release_record_artifact_id=release_record_artifact_id,
        assurance_case_id=certificate.assurance_case_id,
        assurance_case_artifact_id=case_artifact_id,
        proof_obligations_artifact_id=proof_artifact_id,
        release_certificate_status=certificate.status,
        release_certificate_blockers=certificate.blockers,
        cutover_blockers=blockers,
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


def _strict_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def _optional_string(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be string or null")
    return value


def _load_json_object(
    artifact_id: str,
    *,
    artifact_store: ArtifactStore,
    schema_name: str,
) -> dict[str, object]:
    try:
        raw = json.loads(artifact_store.read_bytes(artifact_id).decode("utf-8"))
    except (FileNotFoundError, ArtifactIntegrityError) as exc:
        raise ValueError(f"{schema_name} artifact failed integrity verification") from exc
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
        release_scope=str(payload.get("release_scope") or ""), claims=tuple(claims)
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
        artifact_store_backend_id=str(payload.get("artifact_store_backend_id") or ""),
        release_registry_backend_id=str(payload.get("release_registry_backend_id") or ""),
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
        schema_version=_strict_int(payload.get("schema_version"), label="backend schema_version"),
    )
    if qualification.qualification_id != declared:
        raise ValueError("production backend qualification semantic identity mismatch")
    return qualification


def load_production_publication_authorization(
    artifact_id: str,
    *,
    artifact_store: ArtifactStore,
) -> ProductionPublicationAuthorization:
    """Replay and independently re-derive a pre-publication authorization artifact."""

    raw = _load_json_object(
        artifact_id,
        artifact_store=artifact_store,
        schema_name="apex-stored-production-publication-authorization",
    )
    payload = raw.get("payload")
    declared = raw.get("authorization_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("production publication authorization payload/identity is invalid")
    bundle_raw = _optional_string(payload.get("bundle_id"), label="authorization bundle_id")
    world_raw = _optional_string(payload.get("world_id"), label="authorization world_id")
    authorization = ProductionPublicationAuthorization(
        season=str(payload.get("season") or ""),
        entry=_strict_int(payload.get("entry"), label="authorization entry"),
        gameweek=_strict_int(payload.get("gameweek"), label="authorization gameweek"),
        bundle_id=None if bundle_raw is None else BundleId(bundle_raw),
        world_id=None if world_raw is None else GlobalWorldId(world_raw),
        runtime_digest=str(payload.get("runtime_digest") or ""),
        created_at=str(payload.get("created_at") or ""),
        valid_until=_optional_string(
            payload.get("valid_until"),
            label="authorization valid_until",
        ),
        artifact_manifest_id=str(payload.get("artifact_manifest_id") or ""),
        assurance_case_id=str(payload.get("assurance_case_id") or ""),
        assurance_case_artifact_id=str(payload.get("assurance_case_artifact_id") or ""),
        proof_obligations_artifact_id=str(payload.get("proof_obligations_artifact_id") or ""),
        release_certificate_status=str(payload.get("release_certificate_status") or ""),
        release_certificate_blockers=_string_tuple(
            payload.get("release_certificate_blockers"),
            label="authorization certificate blockers",
        ),
        cutover_blockers=_string_tuple(
            payload.get("cutover_blockers"), label="authorization cutover blockers"
        ),
        backend_qualification_id=str(payload.get("backend_qualification_id") or ""),
        backend_qualification_snapshot_artifact_id=str(
            payload.get("backend_qualification_snapshot_artifact_id") or ""
        ),
        backend_qualification_artifact_ids=_string_tuple(
            payload.get("backend_qualification_artifact_ids"),
            label="authorization backend qualification artifacts",
        ),
        schema_version=_strict_int(payload.get("schema_version"), label="authorization schema_version"),
    )
    if authorization.authorization_id != declared:
        raise ValueError("production publication authorization semantic identity mismatch")
    _verify_artifact(
        artifact_store,
        authorization.artifact_manifest_id,
        label="production authorization manifest",
    )
    for backend_artifact in authorization.backend_qualification_artifact_ids:
        _verify_artifact(
            artifact_store,
            backend_artifact,
            label="production authorization backend qualification",
        )
    verified_bundle = _verified_bundle_for_release(
        bundle_id=authorization.bundle_id,
        world_id=authorization.world_id,
        season=authorization.season,
        entry=authorization.entry,
        gameweek=authorization.gameweek,
        store=artifact_store,
    )
    empirical_bindings = _bundle_empirical_bindings(verified_bundle)
    case = _replay_assurance_case(
        authorization.assurance_case_artifact_id, artifact_store=artifact_store
    )
    obligations = _replay_obligations(
        authorization.proof_obligations_artifact_id, artifact_store=artifact_store
    )
    _claim_artifacts(
        case,
        obligations,
        artifact_store,
        season=authorization.season,
        as_of=authorization.created_at,
        empirical_bindings=empirical_bindings,
        verified_bundle=verified_bundle,
    )
    certificate = case.derive_release_certificate(obligations)
    if certificate.assurance_case_id != authorization.assurance_case_id:
        raise ValueError("authorization AssuranceCase identity does not reconcile")
    if certificate.status != authorization.release_certificate_status:
        raise ValueError("authorization ReleaseCertificate status does not reconcile")
    if certificate.blockers != authorization.release_certificate_blockers:
        raise ValueError("authorization ReleaseCertificate blockers do not reconcile")
    qualification = _replay_backend_qualification(
        authorization.backend_qualification_snapshot_artifact_id,
        artifact_store=artifact_store,
    )
    if qualification.qualification_id != authorization.backend_qualification_id:
        raise ValueError("authorization backend qualification identity does not reconcile")
    qualification_artifacts = tuple(
        sorted(
            (
                qualification.artifact_store_qualification_artifact_id,
                qualification.release_registry_qualification_artifact_id,
            )
        )
    )
    if qualification_artifacts != tuple(sorted(authorization.backend_qualification_artifact_ids)):
        raise ValueError("authorization backend qualification evidence does not reconcile")
    expected_blockers = _cutover_blockers(
        season=authorization.season,
        entry=authorization.entry,
        gameweek=authorization.gameweek,
        bundle_id=authorization.bundle_id,
        world_id=authorization.world_id,
        created_at=authorization.created_at,
        valid_until=authorization.valid_until,
        assurance_case=case,
        backend_qualification=qualification,
    )
    if expected_blockers != authorization.cutover_blockers:
        raise ValueError("authorization cutover blockers do not reconcile")
    return authorization


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
    gameweek_raw = payload.get("gameweek")
    ready = payload.get("ready_to_act")
    safe = payload.get("safe_to_act")
    if not isinstance(ready, bool) or not isinstance(safe, bool):
        raise ValueError("production replay ReleaseRecord readiness must be typed booleans")
    record = ReleaseRecord(
        season=str(payload.get("season") or ""),
        entry=_strict_int(payload.get("entry"), label="production replay ReleaseRecord entry"),
        gameweek=(
            None
            if gameweek_raw is None
            else _strict_int(gameweek_raw, label="production replay ReleaseRecord gameweek")
        ),
        bundle_id=_optional_string(payload.get("bundle_id"), label="release bundle_id"),
        world_id=_optional_string(payload.get("world_id"), label="release world_id"),
        runtime_digest=str(payload.get("runtime_digest") or ""),
        created_at=str(payload.get("created_at") or ""),
        valid_until=_optional_string(payload.get("valid_until"), label="release valid_until"),
        status=ReleaseStatus(str(payload.get("status") or "")),
        ready_to_act=ready,
        safe_to_act=safe,
        artifact_manifest_id=str(payload.get("artifact_manifest_id") or ""),
        publication_authorization_artifact_id=_optional_string(
            payload.get("publication_authorization_artifact_id"),
            label="release publication_authorization_artifact_id",
        ),
        superseded_by=_optional_string(payload.get("superseded_by"), label="release superseded_by"),
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
    """Replay a production cutover report and re-derive all proof/authorization state."""

    raw = _load_json_object(
        artifact_id,
        artifact_store=artifact_store,
        schema_name="apex-stored-production-cutover-report",
    )
    payload = raw.get("payload")
    report_id = raw.get("report_id")
    if not isinstance(payload, dict) or not isinstance(report_id, str):
        raise ValueError("stored production cutover report payload/identity is invalid")
    bundle_raw = _optional_string(payload.get("bundle_id"), label="production report bundle_id")
    world_raw = _optional_string(payload.get("world_id"), label="production report world_id")
    report = ProductionCutoverReport(
        season=str(payload.get("season") or ""),
        entry=_strict_int(payload.get("entry"), label="production report entry"),
        gameweek=_strict_int(payload.get("gameweek"), label="production report gameweek"),
        bundle_id=None if bundle_raw is None else BundleId(bundle_raw),
        world_id=None if world_raw is None else GlobalWorldId(world_raw),
        attempt_release_id=ReleaseId(str(payload.get("attempt_release_id") or "")),
        publication_authorization_artifact_id=str(
            payload.get("publication_authorization_artifact_id") or ""
        ),
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
        production_pointer_before=_optional_string(
            payload.get("production_pointer_before"), label="production_pointer_before"
        ),
        production_pointer_after=_optional_string(
            payload.get("production_pointer_after"), label="production_pointer_after"
        ),
        artifact_manifest_id=str(payload.get("artifact_manifest_id") or ""),
        source_artifact_ids=_string_tuple(
            payload.get("source_artifact_ids"), label="source_artifact_ids"
        ),
        status=ProductionCutoverStatus(str(payload.get("status") or "")),
        schema_version=_strict_int(payload.get("schema_version"), label="production report schema_version"),
    )
    if report.report_id != report_id:
        raise ValueError("production cutover report semantic identity mismatch")
    for source_id in report.source_artifact_ids:
        _verify_artifact(artifact_store, source_id, label="production replay source")
    authorization = load_production_publication_authorization(
        report.publication_authorization_artifact_id,
        artifact_store=artifact_store,
    )
    if authorization.assurance_case_id != report.assurance_case_id:
        raise ValueError("replayed production authorization case does not match report")
    if authorization.release_certificate_status != report.release_certificate_status:
        raise ValueError("replayed production authorization certificate does not match report")
    if authorization.release_certificate_blockers != report.release_certificate_blockers:
        raise ValueError("replayed production authorization certificate blockers do not match report")
    if authorization.cutover_blockers != report.cutover_blockers:
        raise ValueError("replayed production authorization cutover blockers do not match report")
    if authorization.backend_qualification_id != report.backend_qualification_id:
        raise ValueError("replayed production authorization backend does not match report")
    record = _replay_release_record(
        report.release_record_artifact_id, artifact_store=artifact_store
    )
    if record.release_id != str(report.attempt_release_id):
        raise ValueError("replayed production ReleaseRecord identity does not match report")
    if record.publication_authorization_artifact_id != report.publication_authorization_artifact_id:
        raise ValueError("replayed ReleaseRecord authorization does not match report")
    if record.created_at != authorization.created_at or record.valid_until != authorization.valid_until:
        raise ValueError("replayed ReleaseRecord validity does not match authorization")
    expected_published = report.status is ProductionCutoverStatus.PUBLISHED
    expected_status = ReleaseStatus.PUBLISHED if expected_published else ReleaseStatus.WITHHELD
    if record.status is not expected_status:
        raise ValueError("replayed production ReleaseRecord status does not match report")
    if record.ready_to_act is not expected_published or record.safe_to_act is not expected_published:
        raise ValueError("replayed production ReleaseRecord readiness does not match cutover status")
    if record.artifact_manifest_id != report.artifact_manifest_id:
        raise ValueError("replayed production ReleaseRecord manifest does not match report")
    if expected_published is not authorization.authorized:
        raise ValueError("production cutover status does not match proof-derived authorization")
    return report
