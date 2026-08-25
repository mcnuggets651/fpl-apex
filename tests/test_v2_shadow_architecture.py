from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "src" / "apex_fpl" / "core" / "shadow.py"
CONTROL = ROOT / "src" / "apex_fpl" / "control" / "shadow_production.py"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            result.append(node.module or "")
    return result


def test_shadow_core_is_dependency_free() -> None:
    forbidden = (
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
    assert [
        name
        for name in _imports(CORE)
        if any(name == item or name.startswith(item + ".") for item in forbidden)
    ] == []


def test_shadow_runner_has_no_network_v1_or_production_write_surface() -> None:
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
    imports = _imports(CONTROL)
    assert [
        name
        for name in imports
        if any(name == item or name.startswith(item + ".") for item in forbidden)
    ] == []
    text = CONTROL.read_text(encoding="utf-8")
    assert "production_reader.compare_and_swap_current" not in text
    assert "production_reader.append(" not in text
    assert "ready_to_act=True" not in text
    assert "safe_to_act=True" not in text
    assert "stage_runtime_release" not in text
    assert "datetime.now(" not in text
    assert "datetime.utcnow(" not in text


def test_shadow_production_uses_assurance_case_and_release_cas_not_independent_readiness_flags() -> None:
    text = CONTROL.read_text(encoding="utf-8")
    assert "derive_release_certificate" in text
    assert "shadow_registry.compare_and_swap_current" in text
    assert "ready_to_act=False" in text
    assert "safe_to_act=False" in text
    assert "CurrentReleaseReader" in text
