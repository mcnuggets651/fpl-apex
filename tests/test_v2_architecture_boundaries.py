from __future__ import annotations

import ast
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "src" / "apex_fpl" / "core"


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
