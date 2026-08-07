#!/usr/bin/env python3
"""Convert Apex projections to the pinned open-fpl-solver CSV contract.

The external solver receives the same official FPL IDs and, by default, the same
ensemble-mean ``xp`` surface used by the Pinnacle maximum-EV optimiser. A legacy
risk-adjusted export can still be requested explicitly.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

POS = {"GK": "G", "DEF": "D", "MID": "M", "FWD": "F"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("players", type=Path)
    parser.add_argument("projections", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--projection-col", default="xp")
    args = parser.parse_args()

    players = pd.read_csv(args.players)
    projections = pd.read_csv(args.projections)
    required_players = {
        "player_id", "web_name", "position", "price", "expected_minutes"
    }
    if not required_players.issubset(players.columns):
        raise ValueError(
            f"players file missing {sorted(required_players - set(players.columns))}"
        )
    projection_col = args.projection_col
    if projection_col not in projections.columns:
        if projection_col == "xp" and "risk_adjusted_xp" in projections.columns:
            projection_col = "risk_adjusted_xp"
        else:
            raise ValueError(f"projection file missing {args.projection_col!r}")
    required_projection = {"player_id", "gw", projection_col}
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
        bad = base.loc[
            base["Pos"].isna(), ["ID", "position"]
        ].head(10).to_dict("records")
        raise ValueError(f"unsupported FPL positions in solver export: {bad}")

    projections["player_id"] = pd.to_numeric(
        projections["player_id"], errors="raise"
    ).astype(int)
    projections["gw"] = pd.to_numeric(
        projections["gw"], errors="raise"
    ).astype(int)
    projections[projection_col] = pd.to_numeric(
        projections[projection_col], errors="coerce"
    ).fillna(0.0)
    gws = sorted(projections["gw"].unique().tolist())
    if not gws:
        raise ValueError("no projected Gameweeks to export")

    xp = projections.pivot_table(
        index="player_id",
        columns="gw",
        values=projection_col,
        aggfunc="sum",
        fill_value=0.0,
    )
    fixture_count = projections.groupby(
        ["player_id", "gw"]
    ).size().unstack(fill_value=0)
    expected_minutes = base.set_index("ID")["expected_minutes"].apply(
        pd.to_numeric, errors="coerce"
    ).fillna(0.0)

    out = base[["ID", "Name", "Pos", "Value"]].copy()
    for gw in gws:
        out[f"{gw}_Pts"] = out["ID"].map(
            xp.get(gw, pd.Series(dtype=float))
        ).fillna(0.0)
        counts = out["ID"].map(
            fixture_count.get(gw, pd.Series(dtype=float))
        ).fillna(0.0)
        counts = np.maximum(counts, 1.0)
        out[f"{gw}_xMins"] = np.clip(
            out["ID"].map(expected_minutes).fillna(0.0) * counts,
            0.0,
            180.0,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False, float_format="%.4f")
    print(
        f"Exported {len(out)} official-ID players on {projection_col} "
        f"for GW={gws} to {args.output}"
    )


if __name__ == "__main__":
    main()
