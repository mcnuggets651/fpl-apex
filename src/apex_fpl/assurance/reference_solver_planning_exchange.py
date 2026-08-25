"""Seal and replay isolated receding-horizon reference-solver I/O."""

from __future__ import annotations

from dataclasses import dataclass
import json

from apex_fpl.control.artifact_store import ArtifactIntegrityError, ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.decision import CandidateUniverse, RationalValue
from apex_fpl.core.decision_policy import DecisionPolicy
from apex_fpl.core.decision_policy_support import (
    CandidatePolicy,
    ChipOptionValuePolicy,
    ContinuationValuePolicy,
    PricePolicy,
)
from apex_fpl.core.forecast import Forecast
from apex_fpl.core.ids import CandidateUniverseId, DecisionInputId, DecisionPolicyId
from apex_fpl.core.manager_state import ManagerState
from apex_fpl.core.planning import RecedingHorizonDecisionResult
from apex_fpl.core.reference_solver_planning_assurance import PlanningReferenceSolverCertificate
from apex_fpl.core.reference_solver_planning_io import (
    PlanningReferenceSolverRequest,
    PlanningReferenceSolverRun,
    PlanningReferenceSolverStatus,
    planning_request_from_payload,
    planning_run_from_payload,
)
from apex_fpl.core.rules import RuleSet


@dataclass(frozen=True, slots=True)
class StoredPlanningReferenceSolverRequest:
    artifact_id: str
    request: PlanningReferenceSolverRequest


@dataclass(frozen=True, slots=True)
class StoredPlanningReferenceSolverRun:
    artifact_id: str
    run: PlanningReferenceSolverRun


@dataclass(frozen=True, slots=True)
class StoredPlanningReferenceSolverCertificate:
    artifact_id: str
    certificate: PlanningReferenceSolverCertificate


def build_planning_reference_solver_request(
    *,
    result: RecedingHorizonDecisionResult,
    manager_state: ManagerState,
    forecast: Forecast,
    candidate_universe: CandidateUniverse,
    ruleset: RuleSet,
    decision_policy: DecisionPolicy,
    continuation_policy: ContinuationValuePolicy,
    chip_option_policy: ChipOptionValuePolicy,
    price_policy: PricePolicy,
    candidate_policy: CandidatePolicy,
    max_search_nodes: int,
) -> PlanningReferenceSolverRequest:
    decision_input = result.decision_input
    if decision_input.manager_state_id != manager_state.manager_state_id:
        raise ValueError("planning reference DecisionInput/ManagerState identity mismatch")
    if decision_input.forecast_id != forecast.forecast_id:
        raise ValueError("planning reference DecisionInput/Forecast identity mismatch")
    if decision_input.candidate_universe_id != candidate_universe.candidate_universe_id:
        raise ValueError("planning reference DecisionInput/CandidateUniverse identity mismatch")
    if decision_input.ruleset_id != ruleset.ruleset_id:
        raise ValueError("planning reference DecisionInput/RuleSet identity mismatch")
    if decision_input.decision_policy_id != decision_policy.decision_policy_id:
        raise ValueError("planning reference DecisionInput/DecisionPolicy identity mismatch")
    return PlanningReferenceSolverRequest.from_semantic_documents(
        decision_input=decision_input.semantic_payload(),
        manager_state=manager_state.semantic_payload(),
        forecast=forecast.semantic_payload(),
        candidate_universe=candidate_universe.semantic_payload(),
        ruleset=ruleset.semantic_payload(),
        decision_policy=decision_policy.semantic_payload(),
        continuation_policy=continuation_policy.semantic_payload(),
        chip_option_policy=chip_option_policy.semantic_payload(),
        price_policy=price_policy.semantic_payload(),
        candidate_policy=candidate_policy.semantic_payload(),
        max_search_nodes=max_search_nodes,
    )


def _store_envelope(
    *,
    schema_name: str,
    semantic_id_name: str,
    semantic_id: str,
    payload: dict[str, object],
    store: ArtifactStore,
) -> str:
    return store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": schema_name,
                "schema_version": 1,
                semantic_id_name: semantic_id,
                "payload": payload,
            }
        ),
        media_type="application/json",
        schema_name=schema_name,
        schema_version="1",
    ).artifact_id


def store_planning_reference_solver_request(
    request: PlanningReferenceSolverRequest,
    *,
    store: ArtifactStore,
) -> StoredPlanningReferenceSolverRequest:
    artifact_id = _store_envelope(
        schema_name="apex-stored-planning-reference-solver-request",
        semantic_id_name="request_id",
        semantic_id=request.request_id,
        payload=request.semantic_payload(),
        store=store,
    )
    return StoredPlanningReferenceSolverRequest(artifact_id, request)


def store_planning_reference_solver_run(
    run: PlanningReferenceSolverRun,
    *,
    store: ArtifactStore,
) -> StoredPlanningReferenceSolverRun:
    artifact_id = _store_envelope(
        schema_name="apex-stored-planning-reference-solver-run",
        semantic_id_name="run_id",
        semantic_id=run.run_id,
        payload=run.semantic_payload(),
        store=store,
    )
    return StoredPlanningReferenceSolverRun(artifact_id, run)


def _read_envelope(
    artifact_id: str,
    *,
    store: ArtifactStore,
    schema_name: str,
    semantic_id_name: str,
) -> tuple[str, dict[str, object]]:
    try:
        raw = store.read_bytes(artifact_id)
    except (ArtifactIntegrityError, FileNotFoundError) as exc:
        raise ValueError(f"{schema_name} artifact failed integrity verification") from exc
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{schema_name} artifact is not valid UTF-8 JSON") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{schema_name} artifact must be object")
    if document.get("schema_name") != schema_name or document.get("schema_version") != 1:
        raise ValueError(f"unsupported {schema_name} artifact schema")
    if canonical_json_bytes(document) != raw:
        raise ValueError(f"{schema_name} artifact is not canonical JSON")
    declared = document.get(semantic_id_name)
    payload = document.get("payload")
    if not isinstance(declared, str) or not isinstance(payload, dict):
        raise ValueError(f"{schema_name} artifact identity/payload is invalid")
    return declared, dict(payload)


def load_planning_reference_solver_request(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> StoredPlanningReferenceSolverRequest:
    declared, payload = _read_envelope(
        artifact_id,
        store=store,
        schema_name="apex-stored-planning-reference-solver-request",
        semantic_id_name="request_id",
    )
    request = planning_request_from_payload(payload)
    if request.request_id != declared:
        raise ValueError("planning reference request semantic identity mismatch")
    return StoredPlanningReferenceSolverRequest(artifact_id, request)


def load_planning_reference_solver_run(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> StoredPlanningReferenceSolverRun:
    declared, payload = _read_envelope(
        artifact_id,
        store=store,
        schema_name="apex-stored-planning-reference-solver-run",
        semantic_id_name="run_id",
    )
    run = planning_run_from_payload(payload)
    if run.run_id != declared:
        raise ValueError("planning reference run semantic identity mismatch")
    return StoredPlanningReferenceSolverRun(artifact_id, run)


def _rational(value) -> RationalValue | None:
    if value is None:
        return None
    return RationalValue(value.numerator, value.denominator)


def _rational_payload(value: object, *, label: str) -> RationalValue | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be object or null")
    numerator = value.get("numerator")
    denominator = value.get("denominator")
    if isinstance(numerator, bool) or not isinstance(numerator, int):
        raise ValueError(f"{label} numerator must be integer")
    if (
        isinstance(denominator, bool)
        or not isinstance(denominator, int)
        or denominator <= 0
    ):
        raise ValueError(f"{label} denominator must be positive integer")
    return RationalValue(numerator, denominator)


def build_planning_reference_solver_certificate(
    *,
    request_artifact_id: str,
    run_artifact_id: str,
    worker_name: str,
    worker_version: str,
    worker_code_artifact_id: str,
    store: ArtifactStore,
) -> PlanningReferenceSolverCertificate:
    request = load_planning_reference_solver_request(request_artifact_id, store=store).request
    run = load_planning_reference_solver_run(run_artifact_id, store=store).run
    if run.request_id != request.request_id:
        raise ValueError("planning reference run does not bind retained request")
    if not store.verify(worker_code_artifact_id):
        raise ValueError("planning reference worker code artifact is missing/corrupt")
    decision_input = request.decision_input
    policy = request.decision_policy
    return PlanningReferenceSolverCertificate(
        decision_input_id=DecisionInputId(canonical_sha256(decision_input)),
        candidate_universe_id=CandidateUniverseId(canonical_sha256(request.candidate_universe)),
        decision_policy_id=DecisionPolicyId(canonical_sha256(policy)),
        worker_name=worker_name,
        worker_version=worker_version,
        solver_contract=request.solver_contract,
        solver_status=run.solver_status,
        best_objective=_rational(run.best_objective),
        best_bound=_rational(run.best_bound),
        gap=_rational(run.gap),
        selected_action_id=run.selected_action_id,
        selected_trajectory_id=run.selected_trajectory_id,
        search_complete=run.search_complete,
        tie_break_policy_id=str(policy.get("tie_break_policy") or ""),
        solver_input_artifact_id=request_artifact_id,
        solver_output_artifact_id=run_artifact_id,
        worker_artifact_id=worker_code_artifact_id,
    )


def verify_planning_reference_solver_certificate_io(
    certificate: PlanningReferenceSolverCertificate,
    *,
    store: ArtifactStore,
) -> tuple[PlanningReferenceSolverRequest, PlanningReferenceSolverRun]:
    request = load_planning_reference_solver_request(
        certificate.solver_input_artifact_id,
        store=store,
    ).request
    run = load_planning_reference_solver_run(
        certificate.solver_output_artifact_id,
        store=store,
    ).run
    if run.request_id != request.request_id:
        raise ValueError("planning reference retained output binds different request")
    rebuilt = build_planning_reference_solver_certificate(
        request_artifact_id=certificate.solver_input_artifact_id,
        run_artifact_id=certificate.solver_output_artifact_id,
        worker_name=certificate.worker_name,
        worker_version=certificate.worker_version,
        worker_code_artifact_id=certificate.worker_artifact_id,
        store=store,
    )
    if rebuilt.semantic_payload() != certificate.semantic_payload():
        raise ValueError("planning reference certificate does not derive from retained worker I/O")
    return request, run


def store_planning_reference_solver_certificate(
    certificate: PlanningReferenceSolverCertificate,
    *,
    store: ArtifactStore,
) -> StoredPlanningReferenceSolverCertificate:
    """Seal a certificate under its semantic identity after replaying retained worker I/O."""

    verify_planning_reference_solver_certificate_io(certificate, store=store)
    ref = store.put_bytes(
        canonical_json_bytes(certificate.semantic_payload()),
        media_type="application/json",
        schema_name="apex-planning-reference-solver-certificate",
        schema_version="1",
    )
    if ref.artifact_id != str(certificate.certificate_id):
        raise ValueError("planning reference certificate storage identity mismatch")
    return StoredPlanningReferenceSolverCertificate(ref.artifact_id, certificate)


def load_planning_reference_solver_certificate(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> StoredPlanningReferenceSolverCertificate:
    """Load a certificate only if semantic identity and retained worker I/O both replay."""

    try:
        raw = store.read_bytes(artifact_id)
    except (ArtifactIntegrityError, FileNotFoundError) as exc:
        raise ValueError("planning reference certificate artifact failed integrity verification") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("planning reference certificate artifact is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("planning reference certificate artifact must be object")
    if payload.get("schema_name") != "apex-planning-reference-solver-certificate":
        raise ValueError("not an Apex planning reference solver certificate")
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported planning reference solver certificate schema")
    if canonical_json_bytes(payload) != raw:
        raise ValueError("planning reference certificate artifact is not canonical JSON")
    search_complete = payload.get("search_complete")
    if not isinstance(search_complete, bool):
        raise ValueError("planning reference certificate search_complete must be boolean")
    certificate = PlanningReferenceSolverCertificate(
        decision_input_id=DecisionInputId(str(payload.get("decision_input_id") or "")),
        candidate_universe_id=CandidateUniverseId(
            str(payload.get("candidate_universe_id") or "")
        ),
        decision_policy_id=DecisionPolicyId(str(payload.get("decision_policy_id") or "")),
        worker_name=str(payload.get("worker_name") or ""),
        worker_version=str(payload.get("worker_version") or ""),
        solver_contract=str(payload.get("solver_contract") or ""),
        solver_status=PlanningReferenceSolverStatus(str(payload.get("solver_status") or "")),
        best_objective=_rational_payload(
            payload.get("best_objective"),
            label="planning reference best_objective",
        ),
        best_bound=_rational_payload(
            payload.get("best_bound"),
            label="planning reference best_bound",
        ),
        gap=_rational_payload(payload.get("gap"), label="planning reference gap"),
        selected_action_id=(
            None
            if payload.get("selected_action_id") is None
            else str(payload.get("selected_action_id"))
        ),
        selected_trajectory_id=(
            None
            if payload.get("selected_trajectory_id") is None
            else str(payload.get("selected_trajectory_id"))
        ),
        search_complete=search_complete,
        tie_break_policy_id=str(payload.get("tie_break_policy_id") or ""),
        solver_input_artifact_id=str(payload.get("solver_input_artifact_id") or ""),
        solver_output_artifact_id=str(payload.get("solver_output_artifact_id") or ""),
        worker_artifact_id=str(payload.get("worker_artifact_id") or ""),
    )
    if str(certificate.certificate_id) != artifact_id:
        raise ValueError("planning reference certificate semantic identity mismatch")
    verify_planning_reference_solver_certificate_io(certificate, store=store)
    return StoredPlanningReferenceSolverCertificate(artifact_id, certificate)
