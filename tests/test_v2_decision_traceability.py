from __future__ import annotations

import ast
from pathlib import Path
import re

import yaml

from apex_fpl.control.proof_registry import ProofRegistry
from apex_fpl.control.requirements_traceability import RequirementsTraceabilityMatrix


ROOT = Path(__file__).resolve().parents[1]
DECISION_PROOF_IDS = {
    "PO-FPL-LEGALITY-001",
    "PO-DECISION-MECHANICS-001",
    "PO-DECISION-SOLVER-EXACTNESS-001",
    "PO-DECISION-POLICY-QUALIFICATION-001",
    "PO-CANDIDATE-UNIVERSE-001",
    "PO-DECISION-REPLAY-001",
}
DECISION_REQUIREMENT_IDS = {
    "REQ-DECISION-SEALED-INPUTS",
    "REQ-DECISION-MECHANICS",
    "REQ-DECISION-SOLVER-EXACTNESS",
    "REQ-DECISION-POLICY-QUALIFICATION",
    "REQ-CANDIDATE-EXACTNESS",
    "REQ-DECISION-REPLAY",
}


def _test_functions() -> set[str]:
    names: set[str] = set()
    for path in (ROOT / "tests").glob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names.update(
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    return names


def _repo_path_exists(value: str) -> bool:
    if value.startswith("slice-"):
        return True
    return (ROOT / value).exists()


def _declared_invariants() -> set[str]:
    text = (ROOT / "docs" / "APEX_INVARIANTS.md").read_text(encoding="utf-8")
    return set(re.findall(r"\*\*(INV-[A-Z0-9-]+)\*\*", text))


def test_slice8_proof_obligations_reference_existing_test_functions() -> None:
    registry = ProofRegistry.load(ROOT / "config" / "proof_obligations.yaml")
    by_id = registry.by_id()
    available_tests = _test_functions()
    assert DECISION_PROOF_IDS.issubset(by_id)
    for proof_id in sorted(DECISION_PROOF_IDS):
        obligation = by_id[proof_id]
        missing = sorted(set(obligation.required_tests) - available_tests)
        assert missing == [], f"{proof_id} references missing tests: {missing}"


def test_slice8_critical_requirements_have_real_routes_and_registered_proofs() -> None:
    proof_registry = ProofRegistry.load(ROOT / "config" / "proof_obligations.yaml")
    matrix = RequirementsTraceabilityMatrix.load(
        ROOT / "config" / "requirements.yaml",
        proof_registry=proof_registry,
    )
    by_id = {row.requirement_id: row for row in matrix.requirements}
    assert DECISION_REQUIREMENT_IDS.issubset(by_id)
    for requirement_id in sorted(DECISION_REQUIREMENT_IDS):
        requirement = by_id[requirement_id]
        assert requirement.critical is True
        assert all(_repo_path_exists(path) for path in requirement.implementation)
        assert all((ROOT / path).exists() for path in requirement.tests)
        assert requirement.proof_obligations


def test_slice8_critical_requirements_reference_declared_invariants() -> None:
    proof_registry = ProofRegistry.load(ROOT / "config" / "proof_obligations.yaml")
    matrix = RequirementsTraceabilityMatrix.load(
        ROOT / "config" / "requirements.yaml",
        proof_registry=proof_registry,
    )
    by_id = {row.requirement_id: row for row in matrix.requirements}
    declared = _declared_invariants()
    assert declared
    for requirement_id in sorted(DECISION_REQUIREMENT_IDS):
        missing = sorted(set(by_id[requirement_id].invariants) - declared)
        assert missing == [], f"{requirement_id} references missing invariants: {missing}"


def test_slice8_traceability_yaml_contains_no_legacy_placeholder_decision_tests() -> None:
    payload = yaml.safe_load(
        (ROOT / "config" / "requirements.yaml").read_text(encoding="utf-8")
    )
    rows = payload["requirements"]
    decision_rows = [
        row
        for row in rows
        if row["requirement_id"] in DECISION_REQUIREMENT_IDS
    ]
    text = "\n".join(
        test
        for row in decision_rows
        for test in row["tests"]
    )
    assert "test_small_universe_optimizer_matches_exhaustive_legal_optimum" not in text
    assert "test_expansion_improvement_invalidates_narrow_exactness" not in text
