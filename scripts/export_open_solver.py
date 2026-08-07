#!/usr/bin/env python3
"""Convert Apex projections to the pinned open-fpl-solver CSV contract.

Usage:
    python scripts/export_open_solver.py reports/players.csv reports/projections.csv output.csv

The external solver is never allowed to remap identity: ``ID`` is the official FPL
player ID already validated by Apex. Its own runtime then re-merges those IDs with
the live official FPL bootstrap before optimisation.
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

POS = {"GK": "G", "DEF": "D", "MID": "M", "FWD": "F"}


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: python scripts/export_open_solver.py players.csv projections.csv output.csv"
        )
    players_path, projections_path, output_path = map(Path, sys.argv[1:4])
    players = pd.read_csv(players_path)
    projections = pd.read_csv(projections_path)
    required_players = {"player_id", "web_name", "position", "price", "expected_minutes"}
    required_projection = {"player_id", "gw", "risk_adjusted_xp"}
    if not required_players.issubset(players.columns):
        raise ValueError(f"players file missing {sorted(required_players - set(players.columns))}")
    if not required_projection.issubset(projections.columns):
        raise ValueError(
            f"projection file missing {sorted(required_projection - set(projections.columns))}"
        )

    base = players.drop_duplicates("player_id").copy()
    base["ID"] = pd.to_numeric(base["player_id"], errors="raise").astype(int)
    base["Name"] = base["web_name"].astype(str)
    base["Pos"] = base["position"].map(POS)
    base["Value"] = pd.to_numeric(base["price"], errors="raise").astype(float)
    if base["Pos"].isna().any():
        bad = base.loc[base["Pos"].isna(), ["ID", "position"]].head(10).to_dict("records")
        raise ValueError(f"unsupported FPL positions in solver export: {bad}")

    projections["player_id"] = pd.to_numeric(projections["player_id"], errors="raise").astype(int)
    projections["gw"] = pd.to_numeric(projections["gw"], errors="raise").astype(int)
    projections["risk_adjusted_xp"] = pd.to_numeric(
        projections["risk_adjusted_xp"], errors="coerce"
    ).fillna(0.0)
    gws = sorted(projections["gw"].unique().tolist())
    if not gws:
        raise ValueError("no projected Gameweeks to export")

    xp = projections.pivot_table(
        index="player_id",
        columns="gw",
        values="risk_adjusted_xp",
        aggfunc="sum",
        fill_value=0.0,
    )
    fixture_count = projections.groupby(["player_id", "gw"]).size().unstack(fill_value=0)
    expected_minutes = base.set_index("ID")["expected_minutes"].apply(
        pd.to_numeric, errors="coerce"
    ).fillna(0.0)

    out = base[["ID", "Name", "Pos", "Value"]].copy()
    for gw in gws:
        out[f"{gw}_Pts"] = out["ID"].map(xp.get(gw, pd.Series(dtype=float))).fillna(0.0)
        counts = out["ID"].map(fixture_count.get(gw, pd.Series(dtype=float))).fillna(0.0)
        # Blank Gameweeks can retain an xMins eligibility signal; points remain
        # exactly zero. Double Gameweeks can legitimately reach 180 xMins.
        counts = np.maximum(counts, 1.0)
        out[f"{gw}_xMins"] = np.clip(
            out["ID"].map(expected_minutes).fillna(0.0) * counts,
            0.0,
            180.0,
        )

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False, float_format="%.4f")
    print(f"Exported {len(out)} official-ID players for GW={gws} to {path}")


if __name__ == "__main__":
    main()
