#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import traceback

import pandas as pd

from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.player_identity import (
    IDENTITY_CONTRACT,
    audit_identity_sources,
    build_official_identity_registry,
    validate_required_id_coverage,
)


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _input_meta(path: Path, frame: pd.DataFrame | None = None) -> dict:
    exists = path.exists() and path.is_file()
    return {
        "path": str(path),
        "exists": exists,
        "size_bytes": int(path.stat().st_size) if exists else None,
        "sha256": _sha256(path),
        "rows": int(len(frame)) if frame is not None else None,
    }


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    frame.to_csv(tmp, index=False)
    os.replace(tmp, path)


def _manifest_snapshot_id(bundle_dir: Path) -> str | None:
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshots = manifest.get("source_snapshot_ids") or {}
    if not isinstance(snapshots, dict):
        return None
    for key in ("official_fpl", "official", "fpl"):
        value = snapshots.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            for nested in ("snapshot_id", "id"):
                nested_value = value.get(nested)
                if isinstance(nested_value, str) and nested_value:
                    return nested_value
    # Preserve the exact manifest content even if the upstream key changes.
    for key, value in snapshots.items():
        if "official" not in str(key).casefold():
            continue
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            nested_value = value.get("snapshot_id") or value.get("id")
            if isinstance(nested_value, str) and nested_value:
                return nested_value
    return None


def _selected_player_ids(payload: object) -> set[int]:
    """Collect only explicitly player-scoped IDs from a recommendation payload."""
    scalar_keys = {"player_id", "captain_id", "vice_captain_id"}
    list_keys = {"player_ids", "squad_ids", "xi_ids", "bench_ids"}
    found: set[int] = set()

    def add(value: object) -> None:
        try:
            if value is not None and not isinstance(value, bool):
                found.add(int(float(value)))
        except (TypeError, ValueError):
            return

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in scalar_keys:
                    add(child)
                elif key in list_keys and isinstance(child, list):
                    for item in child:
                        add(item)
                walk(child)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return found


def _selected_reference_audit(path: Path, official: pd.DataFrame) -> dict:
    registry_ids = set(build_official_identity_registry(official)["player_id"].astype(int))
    if not path.exists():
        return {
            "path": str(path),
            "present": False,
            "reference_count": 0,
            "unknown_ids": [],
            "ready": True,
            "warning": "recommendation not supplied; selected-reference audit not run",
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    selected_ids = _selected_player_ids(payload)
    unknown = sorted(selected_ids - registry_ids)
    return {
        "path": str(path),
        "present": True,
        "sha256": _sha256(path),
        "reference_count": len(selected_ids),
        "player_ids": sorted(selected_ids),
        "unknown_ids": unknown,
        "ready": not unknown,
    }


def _sealed_core_identity(players: pd.DataFrame) -> pd.DataFrame:
    """Recover the exact FPL Core identity witnesses retained in the sealed bundle."""
    if "player_id" not in players.columns:
        return pd.DataFrame()
    candidate_name_cols = [
        col
        for col in ("web_name_core", "source_player_name_core", "player_name_core", "name_core")
        if col in players.columns
    ]
    full_name_available = {"first_name_core", "second_name_core"}.issubset(players.columns)
    if not candidate_name_cols and not full_name_available:
        return pd.DataFrame()

    cols = ["player_id"]
    cols.extend(candidate_name_cols)
    for col in ("first_name_core", "second_name_core", "team_core", "team_name_core", "position_core"):
        if col in players.columns:
            cols.append(col)
    frame = players[cols].copy()
    witness_cols = candidate_name_cols + (["first_name_core", "second_name_core"] if full_name_available else [])
    present = pd.Series(False, index=frame.index)
    for col in witness_cols:
        present |= frame[col].notna() & frame[col].astype(str).str.strip().ne("")
    frame = frame.loc[present].copy()
    if frame.empty:
        return frame

    rename = {
        "web_name_core": "source_player_name",
        "source_player_name_core": "source_player_name",
        "player_name_core": "source_player_name",
        "name_core": "source_player_name",
        "first_name_core": "first_name",
        "second_name_core": "second_name",
        "team_core": "team",
        "team_name_core": "team_name",
        "position_core": "position",
    }
    chosen_name = candidate_name_cols[0] if candidate_name_cols else None
    if chosen_name:
        for col in candidate_name_cols:
            if col != chosen_name and col in frame.columns:
                frame.drop(columns=[col], inplace=True)
        rename[chosen_name] = "source_player_name"
    return frame.rename(columns={k: v for k, v in rename.items() if k in frame.columns})


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument("--airsenal", default="data/generated/airsenal.csv")
    parser.add_argument("--specialist", default="data/manual/specialist_predictions.csv")
    parser.add_argument("--transfer", default="data/manual/transfer_checks.csv")
    parser.add_argument("--availability", default="data/manual/availability.csv")
    parser.add_argument("--tactical", default="data/manual/tactical_roles.csv")
    parser.add_argument("--hierarchy", default="data/manual/squad_hierarchy.csv")
    parser.add_argument("--recommendation", default=None)
    parser.add_argument("--output", default="reports/player_identity_audit.json")
    parser.add_argument("--csv", default="reports/player_identity_audit.csv")
    return parser


def _run(args: argparse.Namespace) -> dict:
    bundle_dir = Path(args.bundle_dir)
    bundle = DecisionBundle.load(bundle_dir)
    players = bundle.to_pipeline_output().players
    registry = build_official_identity_registry(players)
    sources: dict[str, pd.DataFrame] = {}
    blockers: list[str] = []
    warnings: list[str] = []
    inputs: dict[str, dict] = {
        "decision_bundle_manifest": _input_meta(bundle_dir / "manifest.json"),
    }

    core_identity = _sealed_core_identity(players)
    if not core_identity.empty:
        sources["fpl_core"] = core_identity

    air_path = Path(args.airsenal)
    air = pd.DataFrame()
    airsenal_coverage = None
    if bool(bundle.settings.get("source_configuration", {}).get("airsenal_configured")):
        air = _read(air_path)
        inputs["airsenal"] = _input_meta(air_path, air)
        if air.empty:
            blockers.append("configured AIrsenal export is missing or empty for identity audit")
        elif "source_player_name" not in air.columns:
            blockers.append("configured AIrsenal export lacks independent source_player_name witness")
        elif "identity_witness_type" not in air.columns:
            blockers.append("configured AIrsenal export lacks identity_witness_type provenance")
        elif set(air["identity_witness_type"].dropna().astype(str)) != {"airsenal_name"}:
            blockers.append("configured AIrsenal export contains non-authoritative identity witnesses")
        else:
            airsenal_coverage = validate_required_id_coverage(
                players, air, source="airsenal", id_col="player_id"
            )
            blockers.extend(airsenal_coverage.get("blockers") or [])
            # Keep every GW/source row. A later bad row must not be hidden by an
            # earlier correct row for the same player.
            sources["airsenal"] = air
    else:
        inputs["airsenal"] = _input_meta(air_path)

    for name, path in (
        ("fpl_specialist_manual", Path(args.specialist)),
        ("transfer_specialist_manual", Path(args.transfer)),
        ("manual_availability", Path(args.availability)),
        ("manual_tactical_roles", Path(args.tactical)),
        ("manual_squad_hierarchy", Path(args.hierarchy)),
    ):
        frame = _read(path)
        inputs[name] = _input_meta(path, frame)
        if not frame.empty:
            if "source_player_name" not in frame.columns and "web_name" not in frame.columns:
                blockers.append(
                    f"{name} contains player-linked rows without an independent name witness"
                )
            else:
                sources[name] = frame

    audit = audit_identity_sources(players, sources, require_identity_witness=True)
    blockers.extend(audit.get("blockers") or [])
    warnings.extend(audit.get("warnings") or [])

    selected = None
    if args.recommendation:
        recommendation_path = Path(args.recommendation)
        selected = _selected_reference_audit(recommendation_path, players)
        inputs["recommendation"] = _input_meta(recommendation_path)
        if not selected.get("ready", False):
            blockers.append(
                "canonical recommendation references unknown Official FPL player IDs: "
                f"{selected.get('unknown_ids') or []}"
            )

    audit["contract"] = IDENTITY_CONTRACT
    audit["blockers"] = list(dict.fromkeys(blockers))
    audit["warnings"] = list(dict.fromkeys(warnings))
    audit["ready"] = not audit["blockers"]
    audit["decision_bundle_id"] = bundle.bundle_id
    audit["official_snapshot_id"] = _manifest_snapshot_id(bundle_dir)
    audit["official_player_count"] = int(len(registry))
    audit["inputs"] = inputs
    audit["airsenal_full_roster_coverage"] = airsenal_coverage
    audit["selected_references"] = selected
    return audit


def _write_outputs(audit: dict, output: Path, csv_path: Path) -> None:
    _atomic_write_text(output, json.dumps(audit, indent=2, default=str) + "\n")
    rows: list[dict] = []
    for source, result in (audit.get("sources") or {}).items():
        rows.append({"source": source, **result})
    _atomic_write_csv(csv_path, pd.DataFrame(rows))


def main() -> None:
    args = _build_parser().parse_args()
    output = Path(args.output)
    csv_path = Path(args.csv)
    try:
        audit = _run(args)
    except Exception as exc:
        audit = {
            "contract": IDENTITY_CONTRACT,
            "ready": False,
            "decision_bundle_id": None,
            "official_snapshot_id": None,
            "official_player_count": None,
            "sources": {},
            "inputs": {
                "decision_bundle_manifest": _input_meta(Path(args.bundle_dir) / "manifest.json"),
                "airsenal": _input_meta(Path(args.airsenal)),
            },
            "blockers": [f"identity audit internal/load failure: {type(exc).__name__}: {exc}"],
            "warnings": [],
            "failure_kind": "internal_or_input_error",
            "traceback": traceback.format_exc(),
        }
        _write_outputs(audit, output, csv_path)
        print(audit["traceback"], file=__import__("sys").stderr)
        print(json.dumps({"ready": False, "blockers": audit["blockers"]}, indent=2))
        raise SystemExit(1)

    _write_outputs(audit, output, csv_path)
    print(json.dumps({"ready": audit["ready"], "blockers": audit["blockers"]}, indent=2))
    raise SystemExit(0 if audit["ready"] else 1)


if __name__ == "__main__":
    main()
