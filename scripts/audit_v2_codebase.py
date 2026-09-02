from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "apex"


@dataclass(frozen=True)
class Symbol:
    path: str
    kind: str
    name: str
    qualified_name: str
    start_line: int
    end_line: int
    public: bool
    executable_lines: int = 0
    covered_lines: int = 0


def _iter_symbols(path: Path) -> list[Symbol]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel = path.relative_to(ROOT).as_posix()
    symbols: list[Symbol] = []

    def walk(body: list[ast.stmt], prefix: str = "") -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qualified = f"{prefix}.{node.name}" if prefix else node.name
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                symbols.append(
                    Symbol(
                        path=rel,
                        kind=kind,
                        name=node.name,
                        qualified_name=qualified,
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        public=not node.name.startswith("_"),
                    )
                )
                walk(node.body, qualified)

    walk(tree.body)
    return symbols


def _coverage_by_file(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw.get("files", {})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-json", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-zero-public-coverage", action="store_true")
    args = parser.parse_args()

    coverage = _coverage_by_file(args.coverage_json)
    all_symbols: list[Symbol] = []
    files = sorted(SRC.rglob("*.py"))
    total_source_lines = 0

    for path in files:
        text = path.read_text(encoding="utf-8")
        ast.parse(text)
        total_source_lines += len(text.splitlines())
        rel = path.relative_to(ROOT).as_posix()
        file_cov = coverage.get(rel, {})
        executed = set(file_cov.get("executed_lines", []))
        missing = set(file_cov.get("missing_lines", []))
        executable = executed | missing
        for symbol in _iter_symbols(path):
            span = set(range(symbol.start_line, symbol.end_line + 1))
            executable_lines = len(span & executable)
            covered_lines = len(span & executed)
            all_symbols.append(
                Symbol(
                    **{
                        **asdict(symbol),
                        "executable_lines": executable_lines,
                        "covered_lines": covered_lines,
                    }
                )
            )

    zero_public = [
        symbol
        for symbol in all_symbols
        if symbol.public
        and symbol.kind == "function"
        and symbol.executable_lines > 0
        and symbol.covered_lines == 0
    ]
    partial_public = [
        symbol
        for symbol in all_symbols
        if symbol.public
        and symbol.kind == "function"
        and symbol.executable_lines > 0
        and 0 < symbol.covered_lines < symbol.executable_lines
    ]

    report = {
        "source_root": "src/apex",
        "python_files": len(files),
        "source_lines": total_source_lines,
        "functions": sum(s.kind == "function" for s in all_symbols),
        "classes": sum(s.kind == "class" for s in all_symbols),
        "public_functions": sum(
            s.kind == "function" and s.public for s in all_symbols
        ),
        "zero_covered_public_functions": [asdict(s) for s in zero_public],
        "partially_covered_public_functions": [asdict(s) for s in partial_public],
        "symbols": [asdict(s) for s in all_symbols],
    }

    print(
        "Apex V2 inventory: "
        f"{report['python_files']} files, {report['source_lines']} source lines, "
        f"{report['functions']} functions, {report['classes']} classes, "
        f"{report['public_functions']} public functions"
    )
    if coverage:
        print(
            "Zero-covered public functions: "
            f"{len(report['zero_covered_public_functions'])}; "
            "partially covered public functions: "
            f"{len(report['partially_covered_public_functions'])}"
        )
        for symbol in zero_public:
            print(
                f"ZERO {symbol.path}:{symbol.start_line}-{symbol.end_line} "
                f"{symbol.qualified_name}"
            )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    if args.fail_on_zero_public_coverage and zero_public:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
