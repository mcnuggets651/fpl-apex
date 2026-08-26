from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_BUNDLE = ROOT / "src/apex_fpl/core/production_bundle.py"
CONTROL_BUNDLE = ROOT / "src/apex_fpl/control/production_bundle.py"
POLICY_STORE = ROOT / "src/apex_fpl/control/decision_policy_store.py"
MODEL_STORE = ROOT / "src/apex_fpl/control/forecast_model_store.py"
CUTOVER = ROOT / "src/apex_fpl/control/production_cutover.py"
AUTHORITY = ROOT / "src/apex_fpl/control/production_authority.py"


def _absolute_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module)
    return imports


def test_production_bundle_core_contract_is_dependency_free() -> None:
    imports = _absolute_imports(CORE_BUNDLE)
    forbidden = {
        name
        for name in imports
        if name.startswith("apex_fpl.") and not name.startswith("apex_fpl.core.")
    }
    assert forbidden == set()
    text = CORE_BUNDLE.read_text(encoding="utf-8")
    for token in (
        "requests",
        "httpx",
        "pandas",
        "numpy",
        "apex_fpl.services",
        "apex_fpl.optimisation",
        "datetime.now(",
        "datetime.utcnow(",
        "time.time(",
    ):
        assert token not in text


def test_production_bundle_replay_adapters_have_no_network_v1_or_hidden_clock() -> None:
    paths = (CONTROL_BUNDLE, POLICY_STORE, MODEL_STORE)
    imports = set().union(*(_absolute_imports(path) for path in paths))
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
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for token in ("datetime.now(", "datetime.utcnow(", "time.time("):
        assert token not in combined


def test_cutover_and_answer_authority_both_replay_exact_production_bundle() -> None:
    cutover = CUTOVER.read_text(encoding="utf-8")
    authority = AUTHORITY.read_text(encoding="utf-8")
    assert "load_production_planning_bundle" in cutover
    assert "load_production_planning_bundle" in authority
    assert "load_production_decision_bundle" not in cutover
    assert "load_production_decision_bundle" not in authority
    assert "_bundle_empirical_bindings" in cutover
    assert "PRODUCTION_EMPIRICAL_SUBJECT_KIND" in cutover
    assert "qualification_subject_id" in cutover


def test_bundle_contract_pins_direct_decision_lineage_identities() -> None:
    text = CORE_BUNDLE.read_text(encoding="utf-8")
    for field in (
        "forecast_model_id",
        "forecast_id",
        "decision_policy_id",
        "candidate_universe_id",
        "decision_input_id",
        "decision_id",
        "scenario_set_id",
        "robustness_report_id",
    ):
        assert field in text
    assert "canonical_sha256(self.semantic_payload())" in text
