"""Publication-grade replay verification for independent assurance evidence."""

from __future__ import annotations

from dataclasses import dataclass
import json

from apex_fpl.assurance.store import (
    StoredIndependentAssuranceReport,
    load_reference_mechanics_certificate,
    load_reference_solver_certificate,
)
from apex_fpl.assurance.worker_authorization import (
    StoredReferenceSolverAuthorization,
    load_reference_solver_authorization,
)
from apex_fpl.control.artifact_store import ArtifactStore


@dataclass(frozen=True, slots=True)
class VerifiedIndependentAssuranceEvidence:
    """Stored assurance evidence whose cross-links and solver authority replayed."""

    stored_report: StoredIndependentAssuranceReport
    solver_authorization: StoredReferenceSolverAuthorization | None


def _authorization_schema(artifact_id: str, *, store: ArtifactStore) -> bool:
    try:
        payload = json.loads(store.read_bytes(artifact_id).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("schema_name") == "apex-stored-reference-solver-authorization"
    )


def verify_stored_independent_assurance(
    stored: StoredIndependentAssuranceReport,
    *,
    store: ArtifactStore,
) -> VerifiedIndependentAssuranceEvidence:
    """Re-open all release-critical assurance evidence and fail closed on stale authority."""

    report = stored.report
    mechanics = load_reference_mechanics_certificate(
        stored.mechanics_certificate_artifact_id,
        store=store,
    )
    if mechanics.certificate.certificate_id != report.mechanics_certificate_id:
        raise ValueError("verified assurance mechanics certificate does not match report")

    solver = (
        None
        if stored.solver_certificate_artifact_id is None
        else load_reference_solver_certificate(
            stored.solver_certificate_artifact_id,
            store=store,
        )
    )
    if solver is None:
        if report.solver_certificate_id is not None:
            raise ValueError("verified assurance report names missing solver certificate")
    elif solver.certificate.certificate_id != report.solver_certificate_id:
        raise ValueError("verified assurance solver certificate does not match report")

    authorization_ids = tuple(
        artifact_id
        for artifact_id in report.source_artifact_ids
        if _authorization_schema(artifact_id, store=store)
    )
    if len(authorization_ids) > 1:
        raise ValueError("independent assurance report contains multiple solver authorizations")

    authorization: StoredReferenceSolverAuthorization | None = None
    if authorization_ids:
        if solver is None:
            raise ValueError("solver authorization exists without solver certificate")
        authorization = load_reference_solver_authorization(
            authorization_ids[0],
            certificate=solver.certificate,
            store=store,
        )
        required_lineage = {
            authorization.artifact_id,
            authorization.authorization.registry_artifact_id,
            authorization.authorization.worker_code_artifact_id,
            authorization.authorization.qualification_artifact_id,
        }
        missing = sorted(required_lineage - set(report.source_artifact_ids))
        if missing:
            raise ValueError(
                "solver authorization lineage is incomplete in assurance report: "
                + ", ".join(missing)
            )

    if report.publication_eligible and authorization is None:
        raise ValueError(
            "publication-eligible assurance lacks replayable qualified solver authorization"
        )

    return VerifiedIndependentAssuranceEvidence(
        stored_report=stored,
        solver_authorization=authorization,
    )
