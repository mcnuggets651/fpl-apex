from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = ROOT / "src" / "apex_fpl" / "core"
CONTROL_DIR = ROOT / "src" / "apex_fpl" / "control"
CORE_FILES = tuple(sorted(CORE_DIR.glob("learning_*.py")))
CONTROL_FILES = tuple(sorted(CONTROL_DIR.glob("learning_*.py")))


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.append(node.module or "")
    return names


def test_learning_core_remains_dependency_free_from_control_and_v1_runtime() -> None:
    forbidden = (
        "apex_fpl.control",
        "apex_fpl.evaluation",
        "apex_fpl.replay",
        "apex_fpl.data",
        "apex_fpl.services",
        "pandas",
        "numpy",
        "scipy",
        "requests",
        "httpx",
        "random",
    )
    violations: list[str] = []
    for path in CORE_FILES:
        for name in _imports(path):
            if any(name == item or name.startswith(item + ".") for item in forbidden):
                violations.append(f"{path.name}: {name}")
    assert violations == []


def test_learning_control_cannot_import_v1_replay_evaluation_or_network_runtime() -> None:
    forbidden = (
        "apex_fpl.evaluation",
        "apex_fpl.replay",
        "apex_fpl.data",
        "apex_fpl.services",
        "pandas",
        "numpy",
        "scipy",
        "requests",
        "httpx",
        "random",
    )
    violations: list[str] = []
    for path in CONTROL_FILES:
        for name in _imports(path):
            if any(name == item or name.startswith(item + ".") for item in forbidden):
                violations.append(f"{path.name}: {name}")
        text = path.read_text(encoding="utf-8")
        for symbol in ("datetime.now(", "datetime.utcnow(", "np.random", "random."):
            if symbol in text:
                violations.append(f"{path.name}: {symbol}")
    assert violations == []


def test_learning_path_is_explicitly_offline_and_has_no_deleted_monolith() -> None:
    assert CORE_FILES
    assert CONTROL_FILES
    assert not (CORE_DIR / "learning.py").exists()
    combined = "\n".join(path.read_text(encoding="utf-8") for path in CORE_FILES + CONTROL_FILES)
    assert "ArtifactStore" in combined
    assert "LearningUseMode" in combined
    assert "ModelPromotionCertificate" in combined
