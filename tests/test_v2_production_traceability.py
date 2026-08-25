from __future__ import annotations

import ast
from pathlib import Path

import yaml

from apex_fpl.core.production import MANDATORY_PRODUCTION_PROOF_IDS


ROOT = Path(__file__).resolve().parents[1]
PROOF_ID = "PO-PRODUCTION-CUTOVER-001"
REQUIREMENT_ID = "REQ-V2-PRODUCTION-CUTOVER"
INVARIANTS = {
    "INV-PRODUCTION-CERTIFICATE-ONLY",
    "INV-PRODUCTION-BACKEND-QUALIFIED",
    "INV-PRODUCTION-CAS-ATOMIC",
    "INV-PRODUCTION-WITHHELD-NON-ACTIONABLE",
    "INV-PRODUCTION-ANSWER-CURRENT-ONLY",
    "INV-PRODUCTION-AUTHORITY-TIME-BOUNDED",
    "INV-PRODUCTION-REPLAY-EXACT",
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


def test_slice13_production_proof_requirement_and_invariant_traceability_is_closed() -> None:
    proofs = _yaml(ROOT / "config" / "proof_obligations.yaml")["proof_obligations"]
    requirements = _yaml(ROOT / "config" / "requirements.yaml")["requirements"]
    assert isinstance(proofs, list) and isinstance(requirements, list)

    proof = next(row for row in proofs if row["proof_id"] == PROOF_ID)
    requirement = next(row for row in requirements if row["requirement_id"] == REQUIREMENT_ID)
    assert proof["release_policy"] == "REQUIRED"
    assert proof["scope"] == "production_control_plane_build"
    assert "ProductionCutoverReport" not in set(proof["required_evidence"])
    assert "production_CAS_result" not in set(proof["required_evidence"])
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


def test_production_constitutional_proof_surface_tracks_every_required_obligation() -> None:
    proofs = _yaml(ROOT / "config" / "proof_obligations.yaml")["proof_obligations"]
    assert isinstance(proofs, list)
    required = {
        str(row["proof_id"])
        for row in proofs
        if row.get("release_policy") == "REQUIRED"
    }
    assert set(MANDATORY_PRODUCTION_PROOF_IDS) == required
