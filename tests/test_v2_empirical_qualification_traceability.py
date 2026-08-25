from __future__ import annotations

import ast
from pathlib import Path

import yaml

from apex_fpl.control.empirical_qualification_admission import (
    LEARNING_POLICY_QUALIFICATION_ID,
    SCENARIO_GENERATOR_QUALIFICATION_ID,
    SCENARIO_POLICY_QUALIFICATION_ID,
)
from apex_fpl.core.production import MANDATORY_PRODUCTION_PROOF_IDS
from apex_fpl.core.production_proof_contract import (
    EMPIRICAL_PRODUCTION_PROOF_IDS,
    PRODUCTION_EMPIRICAL_SUBJECT_KIND,
    PRODUCTION_PROOF_CLASSES,
)
from apex_fpl.core.proofs import ProofClass


ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION_TEST_FILES = (
    ROOT / "tests/test_v2_empirical_qualification_plane.py",
    ROOT / "tests/test_v2_empirical_qualification_edges.py",
    ROOT / "tests/test_v2_production_cutover.py",
)


def _yaml(path: str) -> dict[str, object]:
    payload = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _test_names(paths: tuple[Path, ...]) -> set[str]:
    names: set[str] = set()
    for path in paths:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names.update(
            node.name
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    return names


def test_required_proof_classes_and_empirical_subjects_are_constitutionally_complete() -> None:
    payload = _yaml("config/proof_obligations.yaml")
    rows = payload["proof_obligations"]
    assert isinstance(rows, list)
    required = {
        row["proof_id"]: ProofClass(row["proof_class"])
        for row in rows
        if isinstance(row, dict) and row["release_policy"] == "REQUIRED"
    }
    assert set(required) == set(MANDATORY_PRODUCTION_PROOF_IDS)
    assert dict(PRODUCTION_PROOF_CLASSES) == required
    empirical = {
        proof_id
        for proof_id, proof_class in required.items()
        if proof_class is ProofClass.EMPIRICAL_QUALIFICATION
    }
    assert empirical == set(EMPIRICAL_PRODUCTION_PROOF_IDS)
    assert set(PRODUCTION_EMPIRICAL_SUBJECT_KIND) == empirical
    assert dict(PRODUCTION_EMPIRICAL_SUBJECT_KIND) == {
        "PO-FORECAST-QUALIFICATION-001": "apex.forecast-model",
        "PO-DECISION-POLICY-QUALIFICATION-001": "apex.decision-policy",
        "PO-SCENARIO-CONVERGENCE-001": "apex.scenario-convergence",
        "PO-MODEL-EVALUATION-001": "apex.model-evaluation",
        "PO-MODEL-PROMOTION-001": "apex.model-promotion",
    }


def test_internal_registry_qualification_ids_cannot_become_release_proof_ids() -> None:
    internal = {
        SCENARIO_GENERATOR_QUALIFICATION_ID,
        SCENARIO_POLICY_QUALIFICATION_ID,
        LEARNING_POLICY_QUALIFICATION_ID,
    }
    assert internal.isdisjoint(MANDATORY_PRODUCTION_PROOF_IDS)
    assert internal.isdisjoint(PRODUCTION_EMPIRICAL_SUBJECT_KIND)


def test_default_experiment_registry_contains_no_fabricated_production_experiment() -> None:
    payload = _yaml("config/experiments_v2.yaml")
    assert payload == {
        "schema_version": 1,
        "season": "2026-2027",
        "experiments": [],
    }


def test_empirical_requirement_covers_contract_implementation_and_proofs() -> None:
    payload = _yaml("config/requirements.yaml")
    rows = payload["requirements"]
    assert isinstance(rows, list)
    requirement = next(
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("requirement_id") == "REQ-V2-EMPIRICAL-QUALIFICATION"
    )
    assert requirement["critical"] is True
    assert {
        "INV-EMPIRICAL-QUALIFICATION-TYPED",
        "INV-EMPIRICAL-PREDECLARED-NO-HINDSIGHT",
        "INV-EMPIRICAL-QUALIFICATION-IDENTITY",
        "INV-EMPIRICAL-RELEASE-SUBJECT-BOUND",
        "INV-PRODUCTION-PROOF-CLASS-PINNED",
    }.issubset(requirement["invariants"])
    assert {
        "src/apex_fpl/core/experiments.py",
        "src/apex_fpl/core/production_proof_contract.py",
        "src/apex_fpl/control/experiment_registry.py",
        "src/apex_fpl/control/empirical_qualification_admission.py",
        "src/apex_fpl/control/production_cutover.py",
        "config/experiments_v2.yaml",
        "docs/APEX_EMPIRICAL_QUALIFICATION_V2.md",
    }.issubset(requirement["implementation"])
    assert set(EMPIRICAL_PRODUCTION_PROOF_IDS).issubset(requirement["proof_obligations"])
    assert "PO-PRODUCTION-CUTOVER-001" in requirement["proof_obligations"]


def test_empirical_proof_required_tests_exist_in_registered_test_files() -> None:
    payload = _yaml("config/proof_obligations.yaml")
    rows = payload["proof_obligations"]
    assert isinstance(rows, list)
    proof_map = {
        row["proof_id"]: row
        for row in rows
        if isinstance(row, dict)
    }
    implemented = _test_names(QUALIFICATION_TEST_FILES)
    empirical_tests = {
        test_name
        for proof_id in EMPIRICAL_PRODUCTION_PROOF_IDS
        for test_name in proof_map[proof_id]["required_tests"]
        if test_name.startswith(
            (
                "test_supported_certificate_",
                "test_typed_admission_",
                "test_production_empirical_proof_",
                "test_structural_mismatch_",
            )
        )
    }
    assert empirical_tests
    assert empirical_tests <= implemented
    cutover_tests = {
        "test_proof_class_laundering_is_rejected_before_pointer_write",
        "test_random_artifact_cannot_satisfy_empirical_production_proof",
        "test_production_proof_class_contract_exactly_matches_required_yaml",
        "test_qualification_subject_identity_ignores_only_qualification_attachment",
        "test_experiment_must_be_predeclared_before_evaluation_window",
    }
    assert cutover_tests <= set(proof_map["PO-PRODUCTION-CUTOVER-001"]["required_tests"])
    assert cutover_tests <= implemented


def test_empirical_core_and_cutover_static_boundaries_are_present() -> None:
    experiment_source = (ROOT / "src/apex_fpl/core/experiments.py").read_text(encoding="utf-8")
    contract_source = (ROOT / "src/apex_fpl/core/production_proof_contract.py").read_text(
        encoding="utf-8"
    )
    cutover_source = (ROOT / "src/apex_fpl/control/production_cutover.py").read_text(
        encoding="utf-8"
    )
    reference_solver_source = (
        ROOT / "src/apex_fpl/control/reference_solver_registry.py"
    ).read_text(encoding="utf-8")

    assert "PRODUCTION_EMPIRICAL_SUBJECT_KIND" in experiment_source
    assert "_validate_production_empirical_subject" in experiment_source
    assert "PRODUCTION_PROOF_CLASSES" in contract_source
    assert "load_empirical_qualification_certificate" in cutover_source
    assert "mandatory production proof class drifted" in cutover_source
    assert "empirical_qualification_admission" not in reference_solver_source
