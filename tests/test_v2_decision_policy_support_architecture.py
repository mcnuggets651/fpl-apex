from __future__ import annotations

import ast
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CORE_SUPPORT = ROOT / "src/apex_fpl/core/decision_policy_support.py"
NUMERIC_POLICY = ROOT / "src/apex_fpl/core/numeric_policy.py"
CONTROL_SUPPORT = ROOT / "src/apex_fpl/control/decision_policy_support.py"
REGISTRY = ROOT / "src/apex_fpl/control/decision_policy_registry.py"


def _absolute_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module)
    return imports


def test_decision_policy_support_core_is_dependency_free() -> None:
    for path in (CORE_SUPPORT, NUMERIC_POLICY):
        imports = _absolute_imports(path)
        forbidden = {
            name
            for name in imports
            if name.startswith("apex_fpl.") and not name.startswith("apex_fpl.core.")
        }
        assert forbidden == set(), (path.name, forbidden)
        text = path.read_text(encoding="utf-8")
        for token in (
            "requests",
            "httpx",
            "pandas",
            "numpy",
            "apex_fpl.services",
            "apex_fpl.optimisation",
            "datetime.now(",
            "datetime.utcnow(",
        ):
            assert token not in text, (path.name, token)


def test_decision_policy_support_control_has_no_network_v1_or_hidden_clock() -> None:
    imports = _absolute_imports(CONTROL_SUPPORT) | _absolute_imports(REGISTRY)
    forbidden_prefixes = (
        "apex_fpl.data",
        "apex_fpl.services",
        "apex_fpl.models",
        "apex_fpl.optimisation",
        "pandas",
        "numpy",
        "requests",
        "httpx",
    )
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in imports
        for prefix in forbidden_prefixes
    )
    combined = CONTROL_SUPPORT.read_text(encoding="utf-8") + REGISTRY.read_text(
        encoding="utf-8"
    )
    assert "datetime.now(" not in combined
    assert "datetime.utcnow(" not in combined


def test_existing_decision_policy_qualification_requirement_governs_typed_supports() -> None:
    payload = yaml.safe_load((ROOT / "config/requirements.yaml").read_text(encoding="utf-8"))
    requirements = {
        row["requirement_id"]: row for row in payload["requirements"]
    }
    row = requirements["REQ-DECISION-POLICY-QUALIFICATION"]
    requirement = str(row["requirement"])
    for semantic in (
        "receding horizon",
        "continuation value",
        "chip option value",
        "price policy",
        "candidate policy",
        "tie-breaking identity",
    ):
        assert semantic in requirement
    assert "INV-DECISION-POLICY-IDENTITY" in row["invariants"]
    assert "INV-DECISION-POLICY-QUALIFIED" in row["invariants"]
    assert "PO-DECISION-POLICY-QUALIFICATION-001" in row["proof_obligations"]
    assert "PO-ARTIFACT-INTEGRITY-001" in row["proof_obligations"]


def test_policy_identity_payload_exposes_numeric_and_all_support_artifacts() -> None:
    source = (ROOT / "src/apex_fpl/core/decision_policy.py").read_text(encoding="utf-8")
    for field in (
        '"numeric_policy_id"',
        '"continuation_value_artifact_id"',
        '"chip_option_value_artifact_id"',
        '"price_policy_artifact_id"',
        '"candidate_policy_artifact_id"',
        '"tie_break_policy"',
    ):
        assert field in source
