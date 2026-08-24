from __future__ import annotations

import ast
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "src" / "apex_fpl" / "core"
MANAGER_V2 = (
    ROOT / "src" / "apex_fpl" / "acquisition" / "sealed_manager.py",
    ROOT / "src" / "apex_fpl" / "control" / "initial_manager_basis.py",
    ROOT / "src" / "apex_fpl" / "control" / "manager_state_from_seals.py",
    ROOT / "src" / "apex_fpl" / "control" / "manager_state_reconstruction.py",
    ROOT / "src" / "apex_fpl" / "control" / "manager_state_override.py",
)
FEATURE_V2 = (
    ROOT / "src" / "apex_fpl" / "control" / "feature_snapshot.py",
    ROOT / "src" / "apex_fpl" / "control" / "feature_batch.py",
    ROOT / "src" / "apex_fpl" / "control" / "feature_assembly.py",
    ROOT / "src" / "apex_fpl" / "control" / "official_features.py",
    ROOT / "src" / "apex_fpl" / "control" / "outcome_truth_registry.py",
)


def test_constitutional_core_depends_only_on_stdlib_or_core() -> None:
    forbidden: list[str] = []
    for path in sorted(CORE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                names = [node.module or ""]
            else:
                continue
            for name in names:
                root = name.split(".", maxsplit=1)[0]
                if root == "apex_fpl" and name.startswith("apex_fpl.core"):
                    continue
                if root not in sys.stdlib_module_names:
                    forbidden.append(f"{path.name}: {name}")
    assert forbidden == []


def test_core_domain_logic_has_no_wall_clock_reads() -> None:
    for path in sorted(CORE.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "datetime.now(" not in text, path.name
        assert "datetime.utcnow(" not in text, path.name


def test_v2_manager_state_path_cannot_depend_on_v1_cache_services_or_dataframe_runtime() -> None:
    forbidden_modules = {
        "apex_fpl.data",
        "apex_fpl.services",
        "pandas",
    }
    violations: list[str] = []
    for path in MANAGER_V2:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if any(
                    name == forbidden or name.startswith(forbidden + ".")
                    for forbidden in forbidden_modules
                ):
                    violations.append(f"{path.name}: {name}")
        text = path.read_text(encoding="utf-8")
        for forbidden_symbol in ("CachedHttp", "services.team_state", "data.http"):
            if forbidden_symbol in text:
                violations.append(f"{path.name}: {forbidden_symbol}")
    assert violations == []


def test_v2_feature_path_has_no_network_wall_clock_dataframe_or_v1_service_dependency() -> None:
    forbidden_modules = {
        "apex_fpl.data",
        "apex_fpl.services",
        "pandas",
        "requests",
        "httpx",
    }
    violations: list[str] = []
    for path in FEATURE_V2:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if any(
                    name == forbidden or name.startswith(forbidden + ".")
                    for forbidden in forbidden_modules
                ):
                    violations.append(f"{path.name}: {name}")
        text = path.read_text(encoding="utf-8")
        for forbidden_symbol in (
            "CachedHttp",
            "datetime.now(",
            "datetime.utcnow(",
            "fetch_understat",
            "expected_minutes_override",
        ):
            if forbidden_symbol in text:
                violations.append(f"{path.name}: {forbidden_symbol}")
    assert violations == []
