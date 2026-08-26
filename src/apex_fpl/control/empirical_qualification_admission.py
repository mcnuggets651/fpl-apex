"""Typed empirical qualification admission for production registries.

Production registries may not treat the existence of a SHA as proof that a candidate was
empirically qualified. Registry-level qualifications that feed a broader release proof use
separate internal qualification IDs, preventing them from impersonating the composite
release proof itself.
"""

from __future__ import annotations

from typing import Mapping

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.experiment_registry import load_empirical_qualification_certificate
from apex_fpl.core.experiments import qualification_subject_id


SCENARIO_GENERATOR_QUALIFICATION_ID = "QUAL-SCENARIO-GENERATOR-001"
SCENARIO_POLICY_QUALIFICATION_ID = "QUAL-SCENARIO-POLICY-001"
LEARNING_POLICY_QUALIFICATION_ID = "QUAL-LEARNING-POLICY-001"


def _qualification_subject_payload(
    *,
    qualification_artifact_id: str,
    subject_payload: Mapping[str, object],
    subject_kind: str,
) -> dict[str, object]:
    """Return the immutable empirical subject, excluding self-referential authority fields.

    DecisionPolicy embeds its qualification artifact in its own semantic payload. A
    certificate therefore cannot hash the already-qualified payload without requiring an
    impossible SHA fixed point. The empirical candidate is the exact substantive policy
    before admission: SHADOW with no qualification artifact. Production replay first
    requires that the materialized policy is QUALIFIED by the *same* retained certificate,
    then normalizes only those two authority fields back to the candidate semantics.

    Other subject kinds remain byte-for-byte semantic subjects.
    """

    payload = dict(subject_payload)
    if subject_kind != "apex.decision-policy":
        return payload
    if payload.get("schema_name") != "apex-decision-policy":
        raise ValueError("DecisionPolicy qualification subject has wrong schema")
    if payload.get("qualification_state") != "QUALIFIED":
        raise ValueError("production DecisionPolicy qualification subject must be QUALIFIED")
    if payload.get("qualification_artifact_id") != qualification_artifact_id:
        raise ValueError(
            "production DecisionPolicy does not bind the replayed qualification artifact"
        )
    payload["qualification_state"] = "SHADOW"
    payload["qualification_artifact_id"] = None
    return payload


def verify_typed_empirical_qualification(
    *,
    qualification_artifact_id: str | None,
    subject_payload: Mapping[str, object],
    subject_kind: str,
    proof_id: str,
    season: str,
    as_of: str,
    store: ArtifactStore,
) -> None:
    """Fail closed unless one retained certificate exactly qualifies this subject."""

    if qualification_artifact_id is None:
        raise ValueError("production empirical subject has no qualification artifact")
    certificate = load_empirical_qualification_certificate(
        qualification_artifact_id,
        store=store,
        as_of=as_of,
    )
    qualification_payload = _qualification_subject_payload(
        qualification_artifact_id=qualification_artifact_id,
        subject_payload=subject_payload,
        subject_kind=subject_kind,
    )
    expected_subject_id = qualification_subject_id(qualification_payload)
    if not certificate.supported:
        raise ValueError("empirical qualification certificate is not SUPPORTED")
    if certificate.proof_id != proof_id:
        raise ValueError("empirical qualification proof_id does not match production contract")
    if certificate.subject_kind != subject_kind:
        raise ValueError("empirical qualification subject_kind does not match production contract")
    if certificate.subject_id != expected_subject_id:
        raise ValueError("empirical qualification subject identity does not match candidate semantics")
    if certificate.season != season:
        raise ValueError("empirical qualification season does not match production season")
