"""Seal and replay the data-only exchange with the isolated V2 reference solver worker."""

from __future__ import annotations

from dataclasses import dataclass
import json

from apex_fpl.control.artifact_store import ArtifactIntegrityError, ArtifactStore
from apex_fpl.core.assurance import ReferenceSolverCertificate, ReferenceSolverStatus
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.decision import CandidateUniverse, DecisionInput, RationalValue
from apex_fpl.core.decision_policy import DecisionPolicy
from apex_fpl.core.forecast import Forecast
from apex_fpl.core.manager_state import ManagerState
from apex_fpl.core.reference_solver_io import (
    ExactSolverValue,
    ReferenceSolverRequest,
    ReferenceSolverRun,
    ReferenceSolverRunStatus,
    request_from_payload,
    run_from_payload,
)
from apex_fpl.core.rules import RuleSet


@dataclass(frozen=True, slots=True)
class StoredReferenceSolverRequest:
    artifact_id: str
    request: ReferenceSolverRequest


@dataclass(frozen=True, slots=True)
class StoredReferenceSolverRun:
    artifact_id: str
    run: ReferenceSolverRun


def build_reference_solver_request(
    *,
    decision_input: DecisionInput,
    manager_state: ManagerState,
    forecast: Forecast,
    candidate_universe: CandidateUniverse,
    ruleset: RuleSet,
    decision_policy: DecisionPolicy,
    max_search_nodes: int,
) -> ReferenceSolverRequest:
    """Build one cross-checked sealed request from exact V2 semantic objects."""

    if decision_input.manager_state_id != manager_state.manager_state_id:
        raise ValueError("reference solver DecisionInput/ManagerState identity mismatch")
    if decision_input.forecast_id != forecast.forecast_id:
        raise ValueError("reference solver DecisionInput/Forecast identity mismatch")
    if decision_input.candidate_universe_id != candidate_universe.candidate_universe_id:
        raise ValueError("reference solver DecisionInput/CandidateUniverse identity mismatch")
    if decision_input.ruleset_id != ruleset.ruleset_id:
        raise ValueError("reference solver DecisionInput/RuleSet identity mismatch")
    if decision_input.decision_policy_id != decision_policy.decision_policy_id:
        raise ValueError("reference solver DecisionInput/DecisionPolicy identity mismatch")
    return ReferenceSolverRequest.from_semantic_documents(
        decision_input=decision_input.semantic_payload(),
        manager_state=manager_state.semantic_payload(),
        forecast=forecast.semantic_payload(),
        candidate_universe=candidate_universe.semantic_payload(),
        ruleset=ruleset.semantic_payload(),
        decision_policy=decision_policy.semantic_payload(),
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
    envelope = {
        "schema_name": schema_name,
        "schema_version": 1,
        semantic_id_name: semantic_id,
        "payload": payload,
    }
    return store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name=schema_name,
        schema_version="1",
    ).artifact_id


def store_reference_solver_request(
    request: ReferenceSolverRequest,
    *,
    store: ArtifactStore,
) -> StoredReferenceSolverRequest:
    artifact_id = _store_envelope(
        schema_name="apex-stored-reference-solver-request",
        semantic_id_name="request_id",
        semantic_id=request.request_id,
        payload=request.semantic_payload(),
        store=store,
    )
    return StoredReferenceSolverRequest(artifact_id=artifact_id, request=request)


def store_reference_solver_run(
    run: ReferenceSolverRun,
    *,
    store: ArtifactStore,
) -> StoredReferenceSolverRun:
    artifact_id = _store_envelope(
        schema_name="apex-stored-reference-solver-run",
        semantic_id_name="run_id",
        semantic_id=run.run_id,
        payload=run.semantic_payload(),
        store=store,
    )
    return StoredReferenceSolverRun(artifact_id=artifact_id, run=run)


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
    return declared, payload


def load_reference_solver_request(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> StoredReferenceSolverRequest:
    declared, payload = _read_envelope(
        artifact_id,
        store=store,
        schema_name="apex-stored-reference-solver-request",
        semantic_id_name="request_id",
    )
    request = request_from_payload(payload)
    if request.request_id != declared:
        raise ValueError("reference solver request semantic identity mismatch")
    return StoredReferenceSolverRequest(artifact_id=artifact_id, request=request)


def load_reference_solver_run(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> StoredReferenceSolverRun:
    declared, payload = _read_envelope(
        artifact_id,
        store=store,
        schema_name="apex-stored-reference-solver-run",
        semantic_id_name="run_id",
    )
    run = run_from_payload(payload)
    if run.run_id != declared:
        raise ValueError("reference solver run semantic identity mismatch")
    return StoredReferenceSolverRun(artifact_id=artifact_id, run=run)


def _rational(value: ExactSolverValue | None) -> RationalValue | None:
    if value is None:
        return None
    return RationalValue(value.numerator, value.denominator)


_STATUS = {
    ReferenceSolverRunStatus.OPTIMAL: ReferenceSolverStatus.OPTIMAL,
    ReferenceSolverRunStatus.FEASIBLE: ReferenceSolverStatus.FEASIBLE,
    ReferenceSolverRunStatus.INFEASIBLE: ReferenceSolverStatus.INFEASIBLE,
    ReferenceSolverRunStatus.SOLVER_LIMIT: ReferenceSolverStatus.SOLVER_LIMIT,
    ReferenceSolverRunStatus.ERROR: ReferenceSolverStatus.ERROR,
}


def build_reference_solver_certificate(
    *,
    request_artifact_id: str,
    run_artifact_id: str,
    worker_name: str,
    worker_version: str,
    worker_code_artifact_id: str,
    store: ArtifactStore,
) -> ReferenceSolverCertificate:
    """Construct a certificate only after replaying exact retained input/output bytes."""

    stored_request = load_reference_solver_request(request_artifact_id, store=store)
    stored_run = load_reference_solver_run(run_artifact_id, store=store)
    request = stored_request.request
    run = stored_run.run
    if run.request_id != request.request_id:
        raise ValueError("reference solver run does not bind retained request")
    if not store.verify(worker_code_artifact_id):
        raise ValueError("reference solver worker code artifact is missing/corrupt")
    return ReferenceSolverCertificate(
        decision_input_id=request.decision_input_id,
        candidate_universe_id=request.candidate_universe_id,
        decision_policy_id=request.decision_policy_id,
        worker_name=worker_name,
        worker_version=worker_version,
        solver_status=_STATUS[run.solver_status],
        best_objective=_rational(run.best_objective),
        best_bound=_rational(run.best_bound),
        gap=_rational(run.gap),
        selected_action_id=run.selected_action_id,
        action_surface_complete=run.action_surface_complete,
        tie_break_policy_id=run.tie_break_policy_id,
        solver_input_artifact_id=request_artifact_id,
        solver_output_artifact_id=run_artifact_id,
        worker_artifact_id=worker_code_artifact_id,
    )


def verify_reference_solver_certificate_io(
    certificate: ReferenceSolverCertificate,
    *,
    store: ArtifactStore,
) -> tuple[ReferenceSolverRequest, ReferenceSolverRun]:
    """Replay retained request/output and prove the certificate is exactly derived from them."""

    request = load_reference_solver_request(
        certificate.solver_input_artifact_id,
        store=store,
    ).request
    run = load_reference_solver_run(
        certificate.solver_output_artifact_id,
        store=store,
    ).run
    if run.request_id != request.request_id:
        raise ValueError("reference solver retained output binds a different request")
    rebuilt = build_reference_solver_certificate(
        request_artifact_id=certificate.solver_input_artifact_id,
        run_artifact_id=certificate.solver_output_artifact_id,
        worker_name=certificate.worker_name,
        worker_version=certificate.worker_version,
        worker_code_artifact_id=certificate.worker_artifact_id,
        store=store,
    )
    if rebuilt.semantic_payload() != certificate.semantic_payload():
        raise ValueError("reference solver certificate does not derive from retained worker I/O")
    return request, run
