from __future__ import annotations

import ast
from pathlib import Path

import yaml

from apex_fpl.core.production import MANDATORY_PRODUCTION_PROOF_IDS


ROOT = Path(__file__).resolve().parents[1]
PROOF_ID = "PO-PRODUCTION-CUTOVER-001"
REFERENCE_SOLVER_PROOF_ID = "PO-REFERENCE-SOLVER-PARITY-001"
REQUIREMENT_ID = "REQ-V2-PRODUCTION-CUTOVER"
PLANNER_REQUIREMENT_ID = "REQ-RECEDING-HORIZON-PLANNER"
ASSURANCE_REQUIREMENT_ID = "REQ-INDEPENDENT-DECISION-ASSURANCE"
CUTOVER = ROOT / "src/apex_fpl/control/production_cutover.py"
AUTHORITY = ROOT / "src/apex_fpl/control/production_authority.py"
CHAMPION_AUTHORITY = ROOT / "src/apex_fpl/control/champion_authority.py"
PROMOTION_REPLAY = ROOT / "src/apex_fpl/control/learning_promotion_replay.py"
CHAMPION_DOC = ROOT / "docs/APEX_CHAMPION_AUTHORITY_V2.md"
INVARIANTS = {
    "INV-PRODUCTION-CERTIFICATE-ONLY",
    "INV-PRODUCTION-PLANNING-AUTHORITY",
    "INV-PRODUCTION-CHAMPION-AUTHORITY",
    "INV-PRODUCTION-BACKEND-QUALIFIED",
    "INV-PRODUCTION-CAS-ATOMIC",
    "INV-PRODUCTION-WITHHELD-NON-ACTIONABLE",
    "INV-PRODUCTION-ANSWER-CURRENT-ONLY",
    "INV-PRODUCTION-AUTHORITY-TIME-BOUNDED",
    "INV-PRODUCTION-REPLAY-EXACT",
    "INV-PLANNING-REFERENCE-PARITY",
}
PLANNER_INVARIANTS = {
    "INV-HYPOTHETICAL-STATE-NOT-CURRENT-TRUTH",
    "INV-PLANNING-FULL-OFFICIAL-EXACT",
    "INV-PLANNING-RESULT-REPLAY-EXACT",
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
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def _assert_declared_paths_exist(requirement: dict[str, object]) -> None:
    for relative in requirement["implementation"]:
        assert (ROOT / relative).exists(), relative
    for relative in requirement["tests"]:
        assert (ROOT / relative).exists(), relative


def test_slice13_production_proof_requirement_and_invariant_traceability_is_closed() -> None:
    proofs = _yaml(ROOT / "config/proof_obligations.yaml")["proof_obligations"]
    requirements = _yaml(ROOT / "config/requirements.yaml")["requirements"]
    assert isinstance(proofs, list) and isinstance(requirements, list)

    proof = next(row for row in proofs if row["proof_id"] == PROOF_ID)
    requirement = next(
        row for row in requirements if row["requirement_id"] == REQUIREMENT_ID
    )
    assert proof["release_policy"] == "REQUIRED"
    assert proof["scope"] == "production_control_plane_build"
    assert "ProductionCutoverReport" not in set(proof["required_evidence"])
    assert "production_CAS_result" not in set(proof["required_evidence"])
    assert "ProductionPlanningBundle" in set(proof["required_evidence"])
    assert "PlanningResultId" in set(proof["required_evidence"])
    assert "PlanningReferenceSolverCertificateId" in set(proof["required_evidence"])
    assert "ProductionDecisionBundle" not in set(proof["required_evidence"])
    assert requirement["critical"] is True
    assert PROOF_ID in requirement["proof_obligations"]
    assert REFERENCE_SOLVER_PROOF_ID in requirement["proof_obligations"]
    assert INVARIANTS.issubset(set(requirement["invariants"]))

    invariant_text = (ROOT / "docs/APEX_INVARIANTS.md").read_text(encoding="utf-8")
    for invariant in INVARIANTS:
        assert f"**{invariant}**" in invariant_text

    _assert_declared_paths_exist(requirement)

    available_tests: set[str] = set()
    for relative in requirement["tests"]:
        available_tests |= _test_functions(ROOT / relative)
    missing = set(proof["required_tests"]) - available_tests
    assert missing == set()


def test_cutover_and_answer_authority_both_replay_exact_production_bundle() -> None:
    """Constitutionally own the schema-v2 bundle replay guard under cutover requirement."""

    cutover = CUTOVER.read_text(encoding="utf-8")
    authority = AUTHORITY.read_text(encoding="utf-8")
    assert "load_production_planning_bundle" in cutover
    assert "load_production_planning_bundle" in authority
    assert "load_production_decision_bundle" not in cutover
    assert "load_production_decision_bundle" not in authority


def test_cutover_and_answer_authority_both_replay_exact_champion_authority() -> None:
    cutover = CUTOVER.read_text(encoding="utf-8")
    authority = AUTHORITY.read_text(encoding="utf-8")
    champion = CHAMPION_AUTHORITY.read_text(encoding="utf-8")
    promotion = PROMOTION_REPLAY.read_text(encoding="utf-8")

    assert "verify_bundle_champion_authority(" in cutover
    assert "verify_bundle_champion_authority(" in authority
    assert "verify_model_promotion_replay(" in champion
    assert "registry.verify_policy(" in promotion
    assert "production=True" in promotion
    assert "did not exist at replay as_of" in champion


def test_runtime_publication_paths_are_champion_verifier_only() -> None:
    forbidden = (
        "issue_champion_admission(",
        "create_production_champion_generation(",
        "issue_model_promotion_certificate(",
        "apply_model_promotion(",
    )
    for path in (CUTOVER, AUTHORITY):
        text = path.read_text(encoding="utf-8")
        for symbol in forbidden:
            assert symbol not in text

    champion_doc = CHAMPION_DOC.read_text(encoding="utf-8")
    assert "verifier-only" in champion_doc
    assert "Qualification" in champion_doc
    assert "champion" in champion_doc


def test_champion_authority_is_explicitly_owned_by_production_requirement() -> None:
    requirements = _yaml(ROOT / "config/requirements.yaml")["requirements"]
    assert isinstance(requirements, list)
    requirement = next(
        row for row in requirements if row["requirement_id"] == REQUIREMENT_ID
    )
    assert "INV-PRODUCTION-CHAMPION-AUTHORITY" in set(requirement["invariants"])
    assert {
        "src/apex_fpl/core/champion_authority.py",
        "src/apex_fpl/control/champion_authority.py",
        "src/apex_fpl/control/learning_promotion_replay.py",
        "docs/APEX_CHAMPION_AUTHORITY_V2.md",
    }.issubset(set(requirement["implementation"]))
    assert "tests/test_v2_champion_authority.py" in set(requirement["tests"])
    _assert_declared_paths_exist(requirement)


def test_receding_horizon_planner_has_explicit_constitutional_ownership() -> None:
    requirements = _yaml(ROOT / "config/requirements.yaml")["requirements"]
    assert isinstance(requirements, list)
    planner = next(
        row for row in requirements if row["requirement_id"] == PLANNER_REQUIREMENT_ID
    )
    assert planner["critical"] is True
    assert PLANNER_INVARIANTS.issubset(set(planner["invariants"]))
    assert {
        "src/apex_fpl/core/planning.py",
        "src/apex_fpl/decision/planner.py",
        "src/apex_fpl/decision/planning_store.py",
        "docs/APEX_RECEDING_HORIZON_PLANNER_V2.md",
    }.issubset(set(planner["implementation"]))
    assert {
        "tests/test_v2_receding_planner.py",
        "tests/test_v2_receding_planning_transitions.py",
        "tests/test_v2_planning_store.py",
        "tests/test_v2_production_planning_bundle.py",
    }.issubset(set(planner["tests"]))
    _assert_declared_paths_exist(planner)

    invariant_text = (ROOT / "docs/APEX_INVARIANTS.md").read_text(encoding="utf-8")
    for invariant in PLANNER_INVARIANTS:
        assert f"**{invariant}**" in invariant_text


def test_independent_production_assurance_is_planning_v2_bound() -> None:
    proofs = _yaml(ROOT / "config/proof_obligations.yaml")["proof_obligations"]
    requirements = _yaml(ROOT / "config/requirements.yaml")["requirements"]
    assert isinstance(proofs, list) and isinstance(requirements, list)
    proof = next(
        row for row in proofs if row["proof_id"] == REFERENCE_SOLVER_PROOF_ID
    )
    assurance = next(
        row
        for row in requirements
        if row["requirement_id"] == ASSURANCE_REQUIREMENT_ID
    )

    assert proof["release_policy"] == "REQUIRED"
    evidence = set(proof["required_evidence"])
    assert {
        "PlanningReferenceSolverCertificateId",
        "ReferenceSolverAuthorizationId",
        "PlanningResultId",
        "PlanningTrajectoryId",
    }.issubset(evidence)
    assert "ReferenceSolverCertificateId" not in evidence
    assert "INV-PLANNING-REFERENCE-PARITY" in set(assurance["invariants"])
    assert {
        "src/apex_fpl/assurance/planning_solver_parity.py",
        "src/apex_fpl/control/production_reference_solver_binding.py",
        "src/apex_fpl/workers/reference_solver_planning.py",
    }.issubset(set(assurance["implementation"]))
    assert {
        "tests/test_v2_reference_solver_planning.py",
        "tests/test_v2_reference_solver_planning_qualification.py",
        "tests/test_v2_production_cutover.py",
    }.issubset(set(assurance["tests"]))
    _assert_declared_paths_exist(assurance)


def test_production_constitutional_proof_surface_tracks_every_required_obligation() -> None:
    proofs = _yaml(ROOT / "config/proof_obligations.yaml")["proof_obligations"]
    assert isinstance(proofs, list)
    required = {
        str(row["proof_id"])
        for row in proofs
        if row.get("release_policy") == "REQUIRED"
    }
    assert set(MANDATORY_PRODUCTION_PROOF_IDS) == required
