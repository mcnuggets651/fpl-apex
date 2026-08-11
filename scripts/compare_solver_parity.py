#!/usr/bin/env python3
"""Compare Apex/Pinnacle with a pinned open-fpl-solver result.

Both solvers must receive the same official-ID projection surface. The comparison is
an optimisation-formulation cross-check, never a source-of-truth override.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import sys

import pandas as pd


def _id_set(records: list[dict]) -> set[int]:
    return {int(row["player_id"]) for row in records}


def _unrestricted(report: dict) -> tuple[dict, str]:
    if isinstance(report.get("deterministic_scenarios"), dict):
        return report["deterministic_scenarios"].get("unrestricted", {}), "pinnacle_ev"
    return report.get("scenarios", {}).get("unrestricted", {}), "apex_legacy"


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: python scripts/compare_solver_parity.py apex-or-pinnacle.json solver-result.csv"
        )
    apex_path, solver_path = map(Path, sys.argv[1:3])
    report = json.loads(apex_path.read_text(encoding="utf-8"))
    unrestricted, comparison_surface = _unrestricted(report)
    apex_squad = _id_set(unrestricted.get("squad", []))
    apex_xi = _id_set(unrestricted.get("xi", []))
    apex_cap_records = unrestricted.get("captain", [])
    apex_cap = int(apex_cap_records[0]["player_id"]) if apex_cap_records else None
    if len(apex_squad) != 15 or len(apex_xi) != 11:
        raise ValueError("unrestricted scenario does not contain a legal 15/11 decision")

    external = pd.read_csv(solver_path)
    required = {"id", "week", "lineup", "bench", "captain"}
    missing = required - set(external.columns)
    if missing:
        raise ValueError(f"open-fpl-solver result missing columns: {sorted(missing)}")
    first_gw = int(pd.to_numeric(external["week"], errors="raise").min())
    gw = external[
        pd.to_numeric(external["week"], errors="raise") == first_gw
    ].copy()
    selected = gw[
        (pd.to_numeric(gw["lineup"], errors="coerce").fillna(0) > 0.5)
        | (pd.to_numeric(gw["bench"], errors="coerce").fillna(-1) >= 0)
    ]
    external_squad = set(
        pd.to_numeric(selected["id"], errors="raise").astype(int)
    )
    external_xi = set(
        pd.to_numeric(
            gw[pd.to_numeric(gw["lineup"], errors="coerce").fillna(0) > 0.5]["id"],
            errors="raise",
        ).astype(int)
    )
    cap_rows = gw[
        pd.to_numeric(gw["captain"], errors="coerce").fillna(0) > 0.5
    ]
    external_cap = int(cap_rows.iloc[0]["id"]) if not cap_rows.empty else None
    bundle = report.get("decision_bundle") or {}
    projection_artifact = (bundle.get("artifacts") or {}).get("projections") or {}

    squad_overlap = len(apex_squad & external_squad)
    xi_overlap = len(apex_xi & external_xi)
    payload = {
        "comparison_surface": comparison_surface,
        "projection_surface": "ensemble_mean_xp" if comparison_surface == "pinnacle_ev" else "legacy",
        "gameweek": first_gw,
        "apex_squad": sorted(apex_squad),
        "external_squad": sorted(external_squad),
        "squad_overlap": squad_overlap,
        "squad_overlap_pct": squad_overlap / 15.0,
        "xi_overlap": xi_overlap,
        "xi_overlap_pct": xi_overlap / 11.0,
        "apex_captain": apex_cap,
        "external_captain": external_cap,
        "captain_agrees": apex_cap == external_cap,
        "only_apex": sorted(apex_squad - external_squad),
        "only_external": sorted(external_squad - apex_squad),
        "decision_bundle_id": report.get("decision_bundle_id"),
        "official_snapshot": {
            key: (report.get("official_snapshot") or {}).get(key)
            for key in ("snapshot_id", "bootstrap_sha256", "fixtures_sha256")
        },
        "projection_export_sha256": projection_artifact.get("sha256"),
        "external_solver_result_sha256": hashlib.sha256(solver_path.read_bytes()).hexdigest(),
    }
    output = apex_path.parent / "solver_parity.json"
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
