from __future__ import annotations

from pathlib import Path

import yaml

from apex_fpl.control.proof_registry import ProofRegistry

ROOT = Path(__file__).resolve().parents[1]
SLICE11_PROOFS = {
    "PO-LEARNING-NO-HINDSIGHT-001",
    "PO-MODEL-EVALUATION-001",
    "PO-MODEL-PROMOTION-001",
}
SLICE11_REQUIREMENT = "REQ-LEARNING-GOVERNANCE"


def test_slice11_learning_proofs_and_requirement_are_not_orphaned() -> None:
    registry = ProofRegistry.load(ROOT / "config" / "proof_obligations.yaml")
    by_id = registry.by_id()
    assert SLICE11_PROOFS <= set(by_id)

    requirements = yaml.safe_load((ROOT / "config" / "requirements.yaml").read_text(encoding="utf-8"))
    rows = requirements["requirements"]
    row = next(item for item in rows if item["requirement_id"] == SLICE11_REQUIREMENT)
    assert row["critical"] is True
    assert SLICE11_PROOFS <= set(row["proof_obligations"])

    invariant_text = (ROOT / "docs" / "APEX_INVARIANTS.md").read_text(encoding="utf-8")
    for invariant_id in row["invariants"]:
        assert f"**{invariant_id}**" in invariant_text

    for path in row["implementation"] + row["tests"]:
        assert (ROOT / path).exists(), path

    proof_ids = set(by_id)
    for proof_id in row["proof_obligations"]:
        assert proof_id in proof_ids


def test_slice11_proof_test_names_resolve_to_real_test_functions() -> None:
    registry = ProofRegistry.load(ROOT / "config" / "proof_obligations.yaml")
    test_source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((ROOT / "tests").glob("test_*.py"))
    )
    for proof_id in SLICE11_PROOFS:
        proof = registry.by_id()[proof_id]
        assert proof.required_tests
        for test_name in proof.required_tests:
            assert f"def {test_name}(" in test_source, (proof_id, test_name)
