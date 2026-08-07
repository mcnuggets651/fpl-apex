#!/usr/bin/env python3
"""Compare Apex's squad with a pinned open-fpl-solver result.

This is a robustness check, not a source-of-truth override. Both solvers receive the
same official-ID Apex projection export. A disagreement is useful diagnostic evidence
about objective/constraint formulation, not permission to bypass the Apex safety gate.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd


def _id_set(records: list[dict]) -> set[int]:
    return {int(row["player_id"]) for row in records}


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: python scripts/compare_solver_parity.py reports/latest.json solver-result.csv"
        )
    apex_path, solver_path = map(Path, sys.argv[1:3])
    report = json.loads(apex_path.read_text())
    unrestricted = report.get("scenarios", {}).get("unrestricted", {})
    apex_squad = _id_set(unrestricted.get("squad", []))
    apex_xi = _id_set(unrestricted.get("xi", []))
    apex_cap_records = unrestricted.get("captain", [])
    apex_cap = int(apex_cap_records[0]["player_id"]) if apex_cap_records else None
    if len(apex_squad) != 15:
        raise ValueError("Apex unrestricted scenario does not contain a legal 15-player squad")

    external = pd.read_csv(solver_path)
    required = {"id", "week", "lineup", "bench", "captain"}
    missing = required - set(external.columns)
    if missing:
        raise ValueError(f"open-fpl-solver result missing columns: {sorted(missing)}")
    first_gw = int(pd.to_numeric(external["week"], errors="raise").min())
    gw = external[pd.to_numeric(external["week"], errors="raise") == first_gw].copy()
    selected = gw[(pd.to_numeric(gw["lineup"], errors="coerce").fillna(0) > 0.5) | (pd.to_numeric(gw["bench"], errors="coerce").fillna(-1) >= 0)]
    external_squad = set(pd.to_numeric(selected["id"], errors="raise").astype(int))
    external_xi = set(
        pd.to_numeric(
            gw[pd.to_numeric(gw["lineup"], errors="coerce").fillna(0) > 0.5]["id"],
            errors="raise",
        ).astype(int)
    )
    cap_rows = gw[pd.to_numeric(gw["captain"], errors="coerce").fillna(0) > 0.5]
    external_cap = int(cap_rows.iloc[0]["id"]) if not cap_rows.empty else None

    squad_overlap = len(apex_squad & external_squad)
    xi_overlap = len(apex_xi & external_xi)
    payload = {
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
    }
    output = apex_path.parent / "solver_parity.json"
    output.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
