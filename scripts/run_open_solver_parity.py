#!/usr/bin/env python3
"""Execute the pinned open-fpl-solver against sealed parity inputs only.

The external optimiser implementation remains untouched. Its mutable FPL HTTP
boundary is replaced at runtime with the bootstrap/fixtures sealed for this exact
DecisionBundle, preventing price/team/position/Gameweek drift during parity.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("contract") != "apex-open-solver-parity-input-v1":
        raise ValueError("unexpected independent parity input contract")
    for name, row in (manifest.get("artifacts") or {}).items():
        path = root / str(row.get("file") or "")
        if not path.is_file() or _sha(path) != row.get("sha256"):
            raise ValueError(f"invalid parity input artifact: {name}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver-root", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--execution-manifest", type=Path, required=True)
    args = parser.parse_args()

    root = args.solver_root.resolve()
    inputs = args.input_dir.resolve()
    manifest = _load_manifest(inputs)
    identity = manifest.get("identity") or {}
    expected_solver = identity.get("external_solver") or {}
    actual_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if actual_sha != expected_solver.get("commit"):
        raise RuntimeError(
            f"independent solver revision mismatch: expected={expected_solver.get('commit')} "
            f"actual={actual_sha}"
        )

    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    source_csv = inputs / "apex.csv"
    if not source_csv.is_file():
        raise FileNotFoundError("sealed parity input is missing apex.csv")
    shutil.copy2(source_csv, data_dir / "apex.csv")

    artifacts = manifest["artifacts"]
    bootstrap = json.loads(
        (inputs / artifacts["official_bootstrap"]["file"]).read_text(encoding="utf-8")
    )
    fixtures = json.loads(
        (inputs / artifacts["official_fixtures"]["file"]).read_text(encoding="utf-8")
    )
    config = inputs / artifacts["solver_config"]["file"]
    gws = [int(gw) for gw in identity.get("gameweeks") or []]
    if not gws:
        raise ValueError("sealed parity input has no Gameweeks")

    sys.path.insert(0, str(root))
    solver_mod = importlib.import_module("dev.solver")
    parser_mod = importlib.import_module("dev.data_parser")
    solve_mod = importlib.import_module("run.solve")

    def sealed_request(url: str, *unused_args: Any, **unused_kwargs: Any) -> Any:
        if str(url).rstrip("/").endswith("bootstrap-static"):
            return bootstrap
        if str(url).rstrip("/").endswith("fixtures"):
            return fixtures
        raise RuntimeError(f"independent parity attempted unsealed HTTP input: {url}")

    # Patch every mutable FPL-data boundary used by the pinned implementation.
    solver_mod.cached_request = sealed_request
    parser_mod.cached_request = sealed_request
    solve_mod.cached_request = sealed_request

    old_argv = sys.argv[:]
    try:
        sys.argv = [
            "run/solve.py",
            "--config", str(config),
            "--datasource", "apex",
            "--horizon", str(len(gws)),
            "--override_next_gw", str(gws[0]),
        ]
        solve_mod.solve_regular()
    finally:
        sys.argv = old_argv

    results = sorted(
        (data_dir / "results").glob("apex_*.csv"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    if not results:
        raise RuntimeError("independent solver produced no Apex result")
    produced = results[0]
    args.result.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(produced, args.result)

    execution = {
        "contract": "apex-open-solver-parity-execution-v1",
        "parity_input_id": manifest.get("parity_input_id"),
        "decision_bundle_id": manifest.get("decision_bundle_id"),
        "external_solver": {
            "repository": expected_solver.get("repository"),
            "commit": actual_sha,
        },
        "gameweeks": gws,
        "input_csv_sha256": _sha(source_csv),
        "result_sha256": _sha(args.result),
        "network_truth_mode": "sealed_official_injection",
    }
    args.execution_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.execution_manifest.write_text(
        json.dumps(execution, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(execution, indent=2))


if __name__ == "__main__":
    main()
