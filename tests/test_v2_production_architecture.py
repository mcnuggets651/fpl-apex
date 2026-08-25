from __future__ import annotations

import ast
import inspect
from pathlib import Path

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.production_authority import resolve_production_answer_authority
from apex_fpl.control.production_cutover import execute_production_cutover
from apex_fpl.control.release_registry import FileSystemReleaseRegistry


ROOT = Path(__file__).resolve().parents[1]
CORE_FILES = (
    ROOT / "src" / "apex_fpl" / "core" / "production.py",
    ROOT / "src" / "apex_fpl" / "core" / "production_authority.py",
    ROOT / "src" / "apex_fpl" / "core" / "production_proof_contract.py",
    ROOT / "src" / "apex_fpl" / "core" / "experiments.py",
    ROOT / "src" / "apex_fpl" / "core" / "production_bundle.py",
)
CUTOVER = ROOT / "src" / "apex_fpl" / "control" / "production_cutover.py"
AUTHORITY = ROOT / "src" / "apex_fpl" / "control" / "production_authority.py"
PLANNING_BUNDLE = ROOT / "src" / "apex_fpl" / "control" / "production_planning_bundle.py"
REFERENCE_SOLVER_BINDING = (
    ROOT / "src" / "apex_fpl" / "control" / "production_reference_solver_binding.py"
)
BACKEND_QUALIFICATION = (
    ROOT / "src" / "apex_fpl" / "control" / "production_backend_qualification.py"
)
EMPIRICAL_ADMISSION = (
    ROOT / "src" / "apex_fpl" / "control" / "empirical_qualification_admission.py"
)
EXPERIMENT_REGISTRY = ROOT / "src" / "apex_fpl" / "control" / "experiment_registry.py"
REFERENCE_SOLVER_REGISTRY = ROOT / "src" / "apex_fpl" / "control" / "reference_solver_registry.py"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            result.append(node.module or "")
    return result


def _forbidden_imports(path: Path) -> list[str]:
    forbidden = (
        "apex_fpl.data",
        "apex_fpl.services",
        "apex_fpl.evaluation",
        "apex_fpl.replay",
        "requests",
        "httpx",
        "pandas",
        "numpy",
        "scipy",
        "random",
    )
    return [
        name
        for name in _imports(path)
        if any(name == item or name.startswith(item + ".") for item in forbidden)
    ]


def test_production_core_contracts_are_dependency_free() -> None:
    core_forbidden = (
        "apex_fpl.control",
        "apex_fpl.data",
        "apex_fpl.services",
        "apex_fpl.evaluation",
        "apex_fpl.replay",
        "requests",
        "httpx",
        "pandas",
        "numpy",
        "scipy",
        "random",
    )
    for path in CORE_FILES:
        imports = _imports(path)
        assert [
            name
            for name in imports
            if any(name == item or name.startswith(item + ".") for item in core_forbidden)
        ] == []


def test_production_cutover_has_no_network_v1_runtime_or_filesystem_backend_shortcut() -> None:
    assert _forbidden_imports(CUTOVER) == []
    text = CUTOVER.read_text(encoding="utf-8")
    assert "FileSystemReleaseRegistry" not in text
    assert "ready_to_act=True" not in text
    assert "safe_to_act=True" not in text
    assert "datetime.now(" not in text
    assert "datetime.utcnow(" not in text
    assert "stage_runtime_release" not in text
    assert "derive_release_certificate" in text
    assert "production_registry.compare_and_swap_current" in text
    assert "ProductionPublicationAuthorization" in text
    assert "_validate_backend_binding" in text
    assert "PRODUCTION_PROOF_CLASSES" in text
    assert "load_empirical_qualification_certificate" in text


def test_production_cutover_requires_schema_v2_planning_bundle_authority() -> None:
    cutover = CUTOVER.read_text(encoding="utf-8")
    planning = PLANNING_BUNDLE.read_text(encoding="utf-8")
    assert "load_production_planning_bundle" in cutover
    assert "VerifiedProductionPlanningBundle" in cutover
    assert "load_production_decision_bundle" not in cutover
    assert "production authority requires schema-v2 planning bundle" in planning
    assert "PlanningSolverStatus.OPTIMAL" in planning
    assert "complete zero-gap optimal planner" in planning
    assert "CandidateUniverseScope.FULL_OFFICIAL" in planning


def test_production_reference_solver_proof_is_planning_bound_and_replay_validated() -> None:
    assert _forbidden_imports(REFERENCE_SOLVER_BINDING) == []
    cutover = CUTOVER.read_text(encoding="utf-8")
    binding = REFERENCE_SOLVER_BINDING.read_text(encoding="utf-8")
    assert "claim_has_matching_planning_reference_solver_parity" in cutover
    assert "REFERENCE_SOLVER_PARITY_PROOF_ID" in cutover
    assert "load_planning_reference_solver_certificate" in binding
    assert "validate_planning_reference_solver_parity" in binding
    assert "load_reference_solver_authorization" in binding
    assert "planning_result_id" in binding
    assert "decision_cutoff" in binding
    assert "horizon_gameweeks" in binding
    assert "load_production_decision_bundle" not in binding
    assert "datetime.now(" not in binding
    assert "datetime.utcnow(" not in binding


def test_empirical_qualification_control_plane_has_no_network_or_v1_runtime_dependency() -> None:
    for path in (EMPIRICAL_ADMISSION, EXPERIMENT_REGISTRY):
        assert _forbidden_imports(path) == []
        text = path.read_text(encoding="utf-8")
        assert "datetime.now(" not in text
        assert "datetime.utcnow(" not in text
        assert "apex_fpl.services.answer_context" not in text
        assert "apex_answer_context.json" not in text


def test_reference_solver_parity_remains_algorithmic_not_empirical_admission() -> None:
    text = REFERENCE_SOLVER_REGISTRY.read_text(encoding="utf-8")
    assert "empirical_qualification_admission" not in text
    assert "ReferenceSolverCertificate" in text or "ReferenceSolverWorker" in text


def test_filesystem_control_plane_is_structurally_reference_only() -> None:
    assert FileSystemArtifactStore.backend_id.startswith("apex.reference.")
    assert FileSystemReleaseRegistry.backend_id.startswith("apex.reference.")


def test_production_backend_qualification_replay_is_independent_and_fail_closed() -> None:
    assert _forbidden_imports(BACKEND_QUALIFICATION) == []
    text = BACKEND_QUALIFICATION.read_text(encoding="utf-8")
    assert "load_production_backend_qualification" in text
    assert "ArtifactIntegrityError" in text
    assert "artifact_store.verify" in text
    assert "ProductionBackendQualification(" in text
    assert "FileSystemArtifactStore" not in text
    assert "FileSystemReleaseRegistry" not in text


def test_production_cutover_accepts_no_independent_readiness_or_safety_input() -> None:
    parameters = inspect.signature(execute_production_cutover).parameters
    assert "ready_to_act" not in parameters
    assert "safe_to_act" not in parameters
    source = inspect.getsource(execute_production_cutover)
    assert "ready_to_act=publishable" in source
    assert "safe_to_act=publishable" in source


def test_answer_authority_is_current_published_v2_only() -> None:
    assert _forbidden_imports(AUTHORITY) == []
    text = AUTHORITY.read_text(encoding="utf-8")
    assert "ReleaseStatus.PUBLISHED" in text
    assert "publication_authorization_artifact_id" in text
    assert "load_production_publication_authorization" in text
    assert "load_production_backend_qualification" in text
    assert text.count("production_registry.current_release_id(key)") >= 2
    assert "current V2 production pointer changed during authority verification" in text
    assert "ReleaseStatus.V1_ACTIONABLE" not in text
    assert "ShadowProduction" not in text
    assert "shadow_registry" not in text


def test_answer_authority_requires_explicit_replayable_time_and_no_hidden_clock() -> None:
    parameters = inspect.signature(resolve_production_answer_authority).parameters
    assert "as_of" in parameters
    text = AUTHORITY.read_text(encoding="utf-8")
    assert "datetime.now(" not in text
    assert "datetime.utcnow(" not in text
    assert "valid_until" in text
    assert "has expired" in text


def test_production_authorization_binds_release_validity_window() -> None:
    core = (ROOT / "src" / "apex_fpl" / "core" / "production.py").read_text(
        encoding="utf-8"
    )
    cutover = CUTOVER.read_text(encoding="utf-8")
    assert "created_at: str" in core
    assert "valid_until: str | None" in core
    assert '"created_at": self.created_at' in core
    assert '"valid_until": self.valid_until' in core
    assert "record.created_at != authorization.created_at" in cutover
    assert "record.valid_until != authorization.valid_until" in cutover


def test_production_authority_does_not_import_legacy_answer_surface() -> None:
    for path in (CUTOVER, AUTHORITY, BACKEND_QUALIFICATION, REFERENCE_SOLVER_BINDING):
        text = path.read_text(encoding="utf-8")
        assert "apex_fpl.services.answer_context" not in text
        assert "apex_answer_context.json" not in text
