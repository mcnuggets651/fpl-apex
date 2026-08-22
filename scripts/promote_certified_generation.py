#!/usr/bin/env python3
"""Promote exactly one coherent Apex run into the repository's latest aliases.

Ready generations require a validated DecisionBundle. A run that fails before a
bundle exists may still promote a teamless NOT READY contract, which is essential:
a fresh catastrophic failure must revoke an older actionable recommendation rather
than leave stale READY state visible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any

from apex_fpl.services.decision_bundle import DecisionBundle, canonical_json_sha256

CONTRACT = "apex-certified-generation-v1"
ALIASES = (
    "apex_recommendation_latest.json",
    "apex_recommendation_latest.md",
    "apex_answer_context.json",
    "pinnacle_latest.json",
    "pinnacle_latest.md",
    "solver_parity.json",
)


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rm(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _same_bundle(payload: dict[str, Any], bundle_id: str, label: str) -> None:
    if str(payload.get("decision_bundle_id") or "") != bundle_id:
        raise ValueError(f"{label} decision_bundle_id does not match sealed bundle")


def validate_generation(run_dir: Path, bundle_dir: Path) -> dict[str, Any]:
    canonical = _load(run_dir / "apex_recommendation_latest.json")
    context = _load(run_dir / "apex_answer_context.json")
    ready = canonical.get("ready_to_act") is True
    if bool(canonical.get("ready_to_act")) != bool(context.get("ready_to_act")):
        raise ValueError("canonical recommendation and answer context readiness disagree")
    if ready and context.get("safe_to_act") is not True:
        raise ValueError("ready canonical generation has unsafe answer context")
    if ready and canonical.get("recommendation") is None:
        raise ValueError("ready canonical generation has no recommendation")
    if not ready:
        if canonical.get("recommendation") is not None:
            raise ValueError("non-ready canonical generation must not expose a recommendation")
        if context.get("safe_to_act") is True:
            raise ValueError("non-ready generation cannot be safe_to_act")

    bundle: DecisionBundle | None = None
    manifest_path = bundle_dir / "manifest.json"
    if manifest_path.is_file():
        bundle = DecisionBundle.load(bundle_dir)
        bundle_id = bundle.bundle_id
        _same_bundle(canonical, bundle_id, "canonical recommendation")
        _same_bundle(context, bundle_id, "answer context")
        canonical_gws = [int(gw) for gw in canonical.get("gameweeks") or []]
        bundle_gws = [int(gw) for gw in bundle.manifest.get("gameweeks") or []]
        if canonical_gws and canonical_gws != bundle_gws:
            raise ValueError(
                f"canonical Gameweeks differ from sealed bundle: canonical={canonical_gws} bundle={bundle_gws}"
            )
    elif ready:
        raise ValueError("a READY generation cannot be certified without a DecisionBundle")
    else:
        if canonical.get("decision_bundle_id") not in (None, ""):
            raise ValueError("non-ready pre-bundle generation names a bundle that is not present")
        if context.get("decision_bundle_id") not in (None, ""):
            raise ValueError("non-ready pre-bundle answer context names a missing bundle")

    if ready:
        assert bundle is not None
        bundle_id = bundle.bundle_id
        pinnacle = _load(run_dir / "pinnacle_latest.json")
        parity = _load(run_dir / "solver_parity.json")
        _same_bundle(pinnacle, bundle_id, "Pinnacle")
        _same_bundle(parity, bundle_id, "solver parity")
        if pinnacle.get("pinnacle_ready") is not True:
            raise ValueError("ready canonical generation has non-ready Pinnacle")
        if (pinnacle.get("pinnacle_gate") or {}).get("ready") is not True:
            raise ValueError("ready canonical generation has failed Pinnacle gate")
        if parity.get("comparison_surface") != "pinnacle_ev":
            raise ValueError("solver parity did not certify the Pinnacle EV surface")
        official = canonical.get("official_snapshot") or {}
        parity_official = parity.get("official_snapshot") or {}
        for field in ("bootstrap_sha256", "fixtures_sha256"):
            if official.get(field) != parity_official.get(field):
                raise ValueError(f"parity {field} does not match canonical snapshot")

    return {"bundle": bundle, "canonical": canonical, "context": context, "ready": ready}


def promote(run_dir: Path, bundle_dir: Path, target_dir: Path, run_id: str) -> dict[str, Any]:
    validated = validate_generation(run_dir, bundle_dir)
    bundle: DecisionBundle | None = validated["bundle"]
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = target_dir.parent / f".{target_dir.name}.promotion-{os.getpid()}"
    _rm(staging)
    staging.mkdir(parents=True)
    try:
        artifacts: dict[str, dict[str, Any]] = {}
        for name in ALIASES:
            source = run_dir / name
            if not source.exists():
                if name in {"apex_recommendation_latest.json", "apex_recommendation_latest.md", "apex_answer_context.json"}:
                    raise FileNotFoundError(source)
                continue
            destination = staging / name
            shutil.copy2(source, destination)
            artifacts[name] = {"sha256": _sha(destination), "bytes": destination.stat().st_size}

        if bundle is not None:
            bundle_manifest = bundle_dir / "manifest.json"
            shutil.copy2(bundle_manifest, staging / "decision_bundle_manifest.json")
            artifacts["decision_bundle_manifest.json"] = {
                "sha256": _sha(staging / "decision_bundle_manifest.json"),
                "bytes": (staging / "decision_bundle_manifest.json").stat().st_size,
            }
            bundle_id: str | None = bundle.bundle_id
            gameweeks = [int(gw) for gw in bundle.manifest.get("gameweeks") or []]
            official_snapshot = bundle.manifest.get("official_snapshot") or {}
            source_tree = (bundle.manifest.get("code") or {}).get("source_tree_sha256")
            configuration = (bundle.manifest.get("code") or {}).get("configuration_sha256")
            settings_sha = (bundle.manifest.get("identity") or {}).get("settings_sha256")
        else:
            bundle_id = None
            gameweeks = [int(gw) for gw in validated["canonical"].get("gameweeks") or []]
            official_snapshot = validated["canonical"].get("official_snapshot") or {}
            source_tree = None
            configuration = None
            settings_sha = None

        identity = {
            "contract": CONTRACT,
            "run_id": str(run_id),
            "decision_bundle_id": bundle_id,
            "ready_to_act": bool(validated["ready"]),
            "gameweeks": gameweeks,
            "official_snapshot": official_snapshot,
            "source_tree_sha256": source_tree,
            "configuration_sha256": configuration,
            "settings_sha256": settings_sha,
            "artifacts": artifacts,
        }
        generation = {"contract": CONTRACT, "generation_id": canonical_json_sha256(identity), **identity}
        (staging / "certified_generation.json").write_text(json.dumps(generation, indent=2) + "\n", encoding="utf-8")
        for name, row in artifacts.items():
            if _sha(staging / name) != row["sha256"]:
                raise RuntimeError(f"staged artifact changed during promotion: {name}")

        target_dir.mkdir(parents=True, exist_ok=True)
        managed = set(ALIASES) | {"decision_bundle_manifest.json", "certified_generation.json"}
        for name in managed:
            destination = target_dir / name
            if destination.exists() and not (staging / name).exists():
                _rm(destination)
        for name in artifacts:
            os.replace(staging / name, target_dir / name)
        os.replace(staging / "certified_generation.json", target_dir / "certified_generation.json")

        published = _load(target_dir / "certified_generation.json")
        for name, row in published["artifacts"].items():
            if _sha(target_dir / name) != row["sha256"]:
                raise RuntimeError(f"published artifact hash mismatch: {name}")
        print(json.dumps(published, indent=2))
        return published
    finally:
        _rm(staging)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path, default=Path("data/generated"))
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    promote(args.run_dir, args.bundle_dir, args.target_dir, args.run_id)


if __name__ == "__main__":
    main()
