from pathlib import Path

import pytest

from apex_fpl.control.proof_registry import ProofRegistry
from apex_fpl.control.requirements_traceability import RequirementsTraceabilityMatrix
from apex_fpl.core.canonical import NonCanonicalValueError, canonical_json_bytes
from apex_fpl.core.proofs import (
    AssuranceCase,
    AssuranceClaim,
    ProofClass,
    ProofObligation,
    ProofStatus,
    ReleasePolicy,
)


ROOT = Path(__file__).resolve().parents[1]


def _obligation(proof_class: ProofClass) -> ProofObligation:
    return ProofObligation(
        proof_id="PO-TEST-001",
        claim="test claim",
        proof_class=proof_class,
        scope="test",
        required_evidence=("evidence",),
        required_tests=("test_route",),
        failure_consequence="block",
        release_policy=ReleasePolicy.REQUIRED,
        owner="tests",
    )


def test_canonical_json_is_order_independent_and_rejects_floats() -> None:
    assert canonical_json_bytes({"b": 2, "a": [True, None]}) == canonical_json_bytes(
        {"a": [True, None], "b": 2}
    )
    with pytest.raises(NonCanonicalValueError):
        canonical_json_bytes({"x": 0.1})


def test_formal_proof_requires_proven_status() -> None:
    case = AssuranceCase(
        release_scope="test",
        claims=(AssuranceClaim("PO-TEST-001", ProofStatus.SUPPORTED),),
    )
    certificate = case.derive_release_certificate(
        [_obligation(ProofClass.FORMAL_INVARIANT)]
    )
    assert certificate.eligible is False
    assert certificate.status == "FAIL"
    assert certificate.blockers


def test_empirical_proof_accepts_supported_but_not_inconclusive() -> None:
    obligation = _obligation(ProofClass.EMPIRICAL_QUALIFICATION)
    supported = AssuranceCase(
        release_scope="test",
        claims=(AssuranceClaim("PO-TEST-001", ProofStatus.SUPPORTED),),
    )
    inconclusive = AssuranceCase(
        release_scope="test",
        claims=(AssuranceClaim("PO-TEST-001", ProofStatus.INCONCLUSIVE),),
    )
    assert supported.derive_release_certificate([obligation]).eligible is True
    assert inconclusive.derive_release_certificate([obligation]).eligible is False


def test_missing_required_proof_fails_closed() -> None:
    case = AssuranceCase(release_scope="test", claims=())
    certificate = case.derive_release_certificate(
        [_obligation(ProofClass.DATA_INTEGRITY_ASSERTION)]
    )
    assert certificate.eligible is False
    assert certificate.blockers == ("missing required proof: PO-TEST-001",)


def test_machine_registries_have_no_critical_orphans() -> None:
    proofs = ProofRegistry.load(ROOT / "config" / "proof_obligations.yaml")
    matrix = RequirementsTraceabilityMatrix.load(
        ROOT / "config" / "requirements.yaml",
        proof_registry=proofs,
    )
    assert proofs.digest.startswith("sha256:")
    assert matrix.digest.startswith("sha256:")
    assert matrix.critical_orphans() == ()
    assert len(proofs.obligations) >= 10
