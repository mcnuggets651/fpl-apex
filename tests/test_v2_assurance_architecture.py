from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSURANCE = (
    ROOT / "src" / "apex_fpl" / "assurance" / "reference_mechanics.py",
    ROOT / "src" / "apex_fpl" / "assurance" / "solver_parity.py",
    ROOT / "src" / "apex_fpl" / "assurance" / "worker_authorization.py",
    ROOT / "src" / "apex_fpl" / "assurance" / "replay_verification.py",
    ROOT / "src" / "apex_fpl" / "assurance" / "case_bridge.py",
    ROOT / "src" / "apex_fpl" / "assurance" / "store.py",
)


def _absolute_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.append(node.module or "")
    return names


def test_v2_independent_assurance_cannot_import_decision_engine_or_v1_runtime() -> None:
    forbidden = {
        "apex_fpl.decision",
        "apex_fpl.optimisation",
        "apex_fpl.services",
        "apex_fpl.data",
        "apex_fpl.models",
        "pandas",
        "numpy",
        "scipy",
        "requests",
        "httpx",
        "random",
    }
    violations: list[str] = []
    for path in ASSURANCE:
        for name in _absolute_imports(path):
            if any(name == item or name.startswith(item + ".") for item in forbidden):
                violations.append(f"{path.name}: {name}")
        text = path.read_text(encoding="utf-8")
        for symbol in (
            "optimise_current_gameweek",
            "optimise_squad_submission",
            "_autosub_weights",
            "_starter_missing_distribution",
            "CachedHttp",
            "datetime.now(",
            "datetime.utcnow(",
        ):
            if symbol in text and not (
                path.name == "reference_mechanics.py"
                and symbol in {"optimise_current_gameweek", "optimise_squad_submission", "_autosub_weights"}
                and symbol in text.split("does not import", maxsplit=1)[-1].split(".", maxsplit=1)[0]
            ):
                violations.append(f"{path.name}: {symbol}")
    # The reference implementation must visibly use exhaustive appearance-state enumeration.
    reference_text = ASSURANCE[0].read_text(encoding="utf-8")
    assert "product((0, 1), repeat=len(uncertain))" in reference_text
    assert violations == []
