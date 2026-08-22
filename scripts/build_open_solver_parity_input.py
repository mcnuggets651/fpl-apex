#!/usr/bin/env python3
"""Build a content-addressed, replayable input for the independent solver.

The independent implementation is deliberately separate from Apex, but it must solve
exactly the same mutable FPL world. This script seals the Official FPL
bootstrap/fixtures that match the DecisionBundle, the exact exported projection CSV,
and a solver configuration derived from the bundle's decision settings/Gameweeks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any

from apex_fpl.config import load_settings
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.official import OfficialFPLClient
from apex_fpl.services.decision_bundle import DecisionBundle, canonical_json_sha256

CONTRACT = "apex-open-solver-parity-input-v1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _config(bundle: DecisionBundle, base: dict[str, Any]) -> dict[str, Any]:
    settings = bundle.settings
    gws = [int(gw) for gw in bundle.manifest.get("gameweeks") or []]
    if not gws:
        raise ValueError("DecisionBundle has no actionable Gameweeks")
    if gws != list(range(gws[0], gws[0] + len(gws))):
        raise ValueError(f"independent solver requires contiguous Gameweeks, got {gws}")
    budget = float(settings.get("budget", 100.0))
    max_per_team = int(settings.get("max_per_team", 3))
    if abs(budget - 100.0) > 1e-9:
        raise ValueError(
            "pinned open-fpl-solver preseason contract has a fixed £100.0m budget; "
            f"refusing false parity against Apex budget={budget}"
        )
    if max_per_team != 3:
        raise ValueError(
            "pinned open-fpl-solver has a fixed three-per-club rule; "
            f"refusing false parity against Apex max_per_team={max_per_team}"
        )
    decay = float(settings.get("fixture_decay", 0.90))
    bench = float(settings.get("approximate_bench_weight", 0.08))
    cfg = dict(base)
    cfg.update(
        {
            "preseason": True,
            "objective": "decay",
            "decay_base": decay,
            "bench_weights": {str(i): bench for i in range(4)},
            "vcap_weight": 0.0,
            "itb_value": 0.0,
            "ft_value": 0.0,
            "ft_value_list": {},
            "ft_use_penalty": 0.0,
            "no_transfer_gws": gws[1:],
            "override_next_gw": gws[0],
            "horizon": len(gws),
            "xmin_lb": 0,
            "ev_per_price_cutoff": 0,
            "keep_top_ev_percent": 100,
            "chip_limits": {"bb": 0, "wc": 0, "fh": 0, "tc": 0},
            "use_bb": [], "use_wc": [], "use_fh": [], "use_tc": [],
            "gap": 0,
            "single_solve": True,
        }
    )
    return cfg


def _validate_manifest(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("contract") != CONTRACT:
        raise ValueError("unexpected parity-input contract")
    artifacts = manifest.get("artifacts") or {}
    for name, row in artifacts.items():
        path = root / str(row.get("file") or "")
        if not path.is_file():
            raise ValueError(f"parity input artifact missing: {name}")
        if _sha(path) != row.get("sha256"):
            raise ValueError(f"parity input artifact hash mismatch: {name}")
    identity = manifest.get("identity") or {}
    if canonical_json_sha256(identity) != manifest.get("parity_input_id"):
        raise ValueError("parity input identity mismatch")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--apex-csv", type=Path, required=True)
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--external-repository", required=True)
    parser.add_argument("--external-sha", required=True)
    args = parser.parse_args()

    bundle = DecisionBundle.load(args.bundle_dir)
    if not args.apex_csv.is_file() or args.apex_csv.stat().st_size == 0:
        raise ValueError("sealed open-solver CSV is missing or empty")
    settings = load_settings()
    official = OfficialFPLClient(CachedHttp(settings.cache_dir)).snapshot(force=False)
    sealed_snapshot = bundle.manifest.get("official_snapshot") or {}
    for field, actual in (("bootstrap_sha256", official.bootstrap_sha256), ("fixtures_sha256", official.fixtures_sha256)):
        expected = str(sealed_snapshot.get(field) or "")
        if actual != expected:
            raise RuntimeError(
                f"Official FPL changed after DecisionBundle seal: {field} bundle={expected} parity={actual}"
            )

    cfg = _config(bundle, json.loads(args.base_config.read_text(encoding="utf-8")))
    target = args.output_dir.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}.staging-{os.getpid()}"
    _remove(staging)
    staging.mkdir(parents=True)
    try:
        files = {
            "official_bootstrap": ("official_bootstrap.json", official.raw_bootstrap),
            "official_fixtures": ("official_fixtures.json", official.raw_fixtures or []),
            "solver_config": ("solver_config.json", cfg),
        }
        artifacts: dict[str, dict[str, str]] = {}
        for name, (filename, payload) in files.items():
            path = staging / filename
            path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            artifacts[name] = {"file": filename, "sha256": _sha(path)}
        shutil.copy2(args.apex_csv, staging / "apex.csv")
        artifacts["projection_csv"] = {"file": "apex.csv", "sha256": _sha(staging / "apex.csv")}

        identity = {
            "contract": CONTRACT,
            "decision_bundle_id": bundle.bundle_id,
            "gameweeks": [int(gw) for gw in bundle.manifest.get("gameweeks") or []],
            "settings_sha256": (bundle.manifest.get("identity") or {}).get("settings_sha256"),
            "official_snapshot": {"bootstrap_sha256": official.bootstrap_sha256, "fixtures_sha256": official.fixtures_sha256},
            "external_solver": {"repository": args.external_repository, "commit": args.external_sha},
            "artifacts": artifacts,
        }
        manifest = {
            "contract": CONTRACT,
            "parity_input_id": canonical_json_sha256(identity),
            "decision_bundle_id": bundle.bundle_id,
            "identity": identity,
            "artifacts": artifacts,
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        _validate_manifest(staging)
        _remove(target)
        staging.replace(target)
        print(json.dumps(_validate_manifest(target), indent=2))
    finally:
        _remove(staging)


if __name__ == "__main__":
    main()
