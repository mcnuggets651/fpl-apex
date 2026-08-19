#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.player_identity import audit_identity_sources


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


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
    # Prefer an explicit Core name column. If the source only carried first+second
    # names the resolver will use those as the independent witness.
    chosen_name = candidate_name_cols[0] if candidate_name_cols else None
    if chosen_name:
        for col in candidate_name_cols:
            if col != chosen_name and col in frame.columns:
                frame.drop(columns=[col], inplace=True)
        rename[chosen_name] = "source_player_name"
    return frame.rename(columns={k: v for k, v in rename.items() if k in frame.columns})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument("--airsenal", default="data/generated/airsenal.csv")
    parser.add_argument("--specialist", default="data/manual/specialist_predictions.csv")
    parser.add_argument("--transfer", default="data/manual/transfer_checks.csv")
    parser.add_argument("--availability", default="data/manual/availability.csv")
    parser.add_argument("--tactical", default="data/manual/tactical_roles.csv")
    parser.add_argument("--hierarchy", default="data/manual/squad_hierarchy.csv")
    parser.add_argument("--output", default="reports/player_identity_audit.json")
    parser.add_argument("--csv", default="reports/player_identity_audit.csv")
    args = parser.parse_args()

    bundle = DecisionBundle.load(args.bundle_dir)
    players = bundle.to_pipeline_output().players
    sources: dict[str, pd.DataFrame] = {}
    blockers: list[str] = []
    warnings: list[str] = []

    core_identity = _sealed_core_identity(players)
    if not core_identity.empty:
        sources["fpl_core"] = core_identity

    air_path = Path(args.airsenal)
    if bool(bundle.settings.get("source_configuration", {}).get("airsenal_configured")):
        air = _read(air_path)
        if air.empty:
            blockers.append("configured AIrsenal export is missing or empty for identity audit")
        elif "source_player_name" not in air.columns:
            blockers.append("configured AIrsenal export lacks independent source_player_name witness")
        elif "identity_witness_type" not in air.columns:
            blockers.append("configured AIrsenal export lacks identity_witness_type provenance")
        elif set(air["identity_witness_type"].dropna().astype(str)) != {"airsenal_name"}:
            blockers.append("configured AIrsenal export contains non-authoritative identity witnesses")
        else:
            # Keep every GW/source row. A later bad row must not be hidden by an
            # earlier correct row for the same player.
            sources["airsenal"] = air

    for name, path in (
        ("fpl_specialist_manual", Path(args.specialist)),
        ("transfer_specialist_manual", Path(args.transfer)),
        ("manual_availability", Path(args.availability)),
        ("manual_tactical_roles", Path(args.tactical)),
        ("manual_squad_hierarchy", Path(args.hierarchy)),
    ):
        frame = _read(path)
        if not frame.empty:
            if "source_player_name" not in frame.columns and "web_name" not in frame.columns:
                blockers.append(
                    f"{name} contains player-linked rows without an independent name witness"
                )
            else:
                # Multiple specialist/source rows per player are legitimate and all
                # must be identity-certified independently.
                sources[name] = frame

    audit = audit_identity_sources(players, sources, require_identity_witness=True)
    blockers.extend(audit.get("blockers") or [])
    warnings.extend(audit.get("warnings") or [])
    audit["blockers"] = list(dict.fromkeys(blockers))
    audit["warnings"] = list(dict.fromkeys(warnings))
    audit["ready"] = not audit["blockers"]
    audit["decision_bundle_id"] = bundle.bundle_id

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

    rows: list[dict] = []
    for source, result in (audit.get("sources") or {}).items():
        rows.append({"source": source, **result})
    pd.DataFrame(rows).to_csv(args.csv, index=False)
    print(json.dumps({"ready": audit["ready"], "blockers": audit["blockers"]}, indent=2))
    raise SystemExit(0 if audit["ready"] else 1)


if __name__ == "__main__":
    main()
