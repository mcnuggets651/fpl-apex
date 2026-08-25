"""Proof obligations, assurance claims and derived release certificates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from .canonical import canonical_sha256


class ProofClass(StrEnum):
    FORMAL_INVARIANT = "FORMAL_INVARIANT"
    ALGORITHMIC_CERTIFICATE = "ALGORITHMIC_CERTIFICATE"
    EMPIRICAL_QUALIFICATION = "EMPIRICAL_QUALIFICATION"
    PROVENANCE_ASSERTION = "PROVENANCE_ASSERTION"
    DATA_INTEGRITY_ASSERTION = "DATA_INTEGRITY_ASSERTION"
    IRREDUCIBLY_UNCERTAIN = "IRREDUCIBLY_UNCERTAIN"


class ProofStatus(StrEnum):
    PROVEN = "PROVEN"
    SUPPORTED = "SUPPORTED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ReleasePolicy(StrEnum):
    REQUIRED = "REQUIRED"
    CONDITIONAL = "CONDITIONAL"
    NON_BLOCKING = "NON_BLOCKING"


@dataclass(frozen=True, slots=True)
class ProofObligation:
    proof_id: str
    claim: str
    proof_class: ProofClass
    scope: str
    required_evidence: tuple[str, ...]
    required_tests: tuple[str, ...]
    failure_consequence: str
    release_policy: ReleasePolicy
    owner: str

    def __post_init__(self) -> None:
        if not self.proof_id.strip():
            raise ValueError("proof_id is required")
        if not self.claim.strip():
            raise ValueError(f"{self.proof_id}: claim is required")
        if self.release_policy is ReleasePolicy.REQUIRED and not self.required_tests:
            raise ValueError(f"{self.proof_id}: required release proof must name a test route")

    def semantic_payload(self) -> dict[str, object]:
        """Canonical durable representation of one release proof obligation."""

        return {
            "proof_id": self.proof_id,
            "claim": self.claim,
            "proof_class": self.proof_class.value,
            "scope": self.scope,
            "required_evidence": list(self.required_evidence),
            "required_tests": list(self.required_tests),
            "failure_consequence": self.failure_consequence,
            "release_policy": self.release_policy.value,
            "owner": self.owner,
        }


@dataclass(frozen=True, slots=True)
class AssuranceClaim:
    proof_id: str
    status: ProofStatus
    evidence_ids: tuple[str, ...] = ()
    test_ids: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    reason: str | None = None

    def semantic_payload(self) -> dict[str, object]:
        return {
            "proof_id": self.proof_id,
            "status": self.status.value,
            "evidence_ids": list(self.evidence_ids),
            "test_ids": list(self.test_ids),
            "artifact_ids": list(self.artifact_ids),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ReleaseCertificate:
    assurance_case_id: str
    eligible: bool
    blockers: tuple[str, ...]
    satisfied_proof_ids: tuple[str, ...]

    @property
    def status(self) -> str:
        return "PASS" if self.eligible else "FAIL"


@dataclass(frozen=True, slots=True)
class AssuranceCase:
    release_scope: str
    claims: tuple[AssuranceClaim, ...]

    def __post_init__(self) -> None:
        ids = [claim.proof_id for claim in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("AssuranceCase contains duplicate proof claims")

    def semantic_payload(self) -> dict[str, object]:
        """Return the exact payload historically used to derive ``case_id``.

        Keeping this shape identical preserves every existing AssuranceCase identity while
        making the release evidence replayable as an immutable semantic object.
        """

        return {
            "release_scope": self.release_scope,
            "claims": [claim.semantic_payload() for claim in self.claims],
        }

    @property
    def case_id(self) -> str:
        return canonical_sha256(self.semantic_payload())

    def derive_release_certificate(
        self,
        obligations: Iterable[ProofObligation],
    ) -> ReleaseCertificate:
        registry = {obligation.proof_id: obligation for obligation in obligations}
        claims = {claim.proof_id: claim for claim in self.claims}
        unknown = sorted(set(claims) - set(registry))
        blockers = [f"unknown proof claim: {proof_id}" for proof_id in unknown]
        satisfied: list[str] = []

        for proof_id, obligation in sorted(registry.items()):
            if obligation.release_policy is ReleasePolicy.NON_BLOCKING:
                continue
            claim = claims.get(proof_id)
            if claim is None:
                if obligation.release_policy is ReleasePolicy.REQUIRED:
                    blockers.append(f"missing required proof: {proof_id}")
                continue
            if _status_satisfies(obligation.proof_class, claim.status):
                satisfied.append(proof_id)
            else:
                blockers.append(
                    f"{proof_id}: {claim.status.value} does not satisfy "
                    f"{obligation.proof_class.value}"
                )

        return ReleaseCertificate(
            assurance_case_id=self.case_id,
            eligible=not blockers,
            blockers=tuple(blockers),
            satisfied_proof_ids=tuple(satisfied),
        )


def _status_satisfies(proof_class: ProofClass, status: ProofStatus) -> bool:
    if proof_class in {
        ProofClass.FORMAL_INVARIANT,
        ProofClass.ALGORITHMIC_CERTIFICATE,
        ProofClass.PROVENANCE_ASSERTION,
        ProofClass.DATA_INTEGRITY_ASSERTION,
    }:
        return status is ProofStatus.PROVEN
    if proof_class in {
        ProofClass.EMPIRICAL_QUALIFICATION,
        ProofClass.IRREDUCIBLY_UNCERTAIN,
    }:
        return status in {ProofStatus.PROVEN, ProofStatus.SUPPORTED}
    return False
