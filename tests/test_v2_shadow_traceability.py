from __future__ import annotations

import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROOF_ID = "PO-SHADOW-PRODUCTION-001"
REQUIREMENT_ID = "REQ-V2-SHADOW-PRODUCTION"
INVARIANTS = {
    "INV-SHADOW-NON-ACTIONABLE",
    "INV-SHADOW-PRODUCTION-POINTER-READ-ONLY",
    "INV-SHADOW-USES-RELEASE-CONTRACT",
    "INV-SHADOW-REPLAY-EXACT",
}


def _yaml(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    }


def test_slice12_shadow_proof_requirement_and_invariant_traceability_is_closed() -> None:
    proofs = _yaml(ROOT / "config" / "proof_obligations.yaml")["proof_obligations"]
    requirements = _yaml(ROOT / "config" / "requirements.yaml")["requirements"]
    assert isinstance(proofs, list) and isinstance(requirements, list)

    proof = next(row for row in proofs if row["proof_id"] == PROOF_ID)
    requirement = next(row for row in requirements if row["requirement_id"] == REQUIREMENT_ID)
    assert proof["release_policy"] == "REQUIRED"
    assert requirement["critical"] is True
    assert PROOF_ID in requirement["proof_obligations"]
    assert INVARIANTS.issubset(set(requirement["invariants"]))

    invariant_text = (ROOT / "docs" / "APEX_INVARIANTS.md").read_text(encoding="utf-8")
    for invariant in INVARIANTS:
        assert f"**{invariant}**" in invariant_text

    for relative in requirement["implementation"]:
        assert (ROOT / relative).exists(), relative
    for relative in requirement["tests"]:
        assert (ROOT / relative).exists(), relative

    available_tests: set[str] = set()
    for relative in requirement["tests"]:
        available_tests |= _test_functions(ROOT / relative)
    missing = set(proof["required_tests"]) - available_tests
    assert missing == set()
