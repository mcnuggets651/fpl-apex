from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd


POS = {"GK": "G", "DEF": "D", "MID": "M", "FWD": "F"}


class SealedSolverBundle(Protocol):
    players: pd.DataFrame
    projections: pd.DataFrame
    manifest: dict
    bundle_id: str


def export_bundle(
    bundle: SealedSolverBundle,
    output: Path,
    projection_col: str = "xp",
) -> None:
    """Export one sealed Apex decision surface to the independent-solver contract.

    Identity, price, position, club and the full projection matrix are read from the
    already validated DecisionBundle. Mutable reports/live APIs are deliberately not
    consulted here, so parity always compares two solvers on one immutable world.
    """
    players = bundle.players
    projections = bundle.projections
    required_players = {
        "player_id",
        "web_name",
        "position",
        "price",
        "expected_minutes",
        "team",
    }
    if not required_players.issubset(players.columns):
        raise ValueError(
            f"sealed players missing {sorted(required_players - set(players.columns))}"
        )
    if projection_col not in projections.columns:
        if projection_col == "xp" and "risk_adjusted_xp" in projections.columns:
            projection_col = "risk_adjusted_xp"
        else:
            raise ValueError(f"sealed projections missing {projection_col!r}")
    required_projection = {"player_id", "gw", projection_col}
    if not required_projection.issubset(projections.columns):
        raise ValueError(
            f"sealed projections missing {sorted(required_projection - set(projections.columns))}"
        )

    base = players.drop_duplicates("player_id").copy()
    if len(base) != len(players):
        raise ValueError("sealed player surface contains duplicate player IDs")
    base["ID"] = pd.to_numeric(base["player_id"], errors="raise").astype(int)
    base["Name"] = base["web_name"].astype(str)
    base["Pos"] = base["position"].map(POS)
    base["Value"] = pd.to_numeric(base["price"], errors="raise").astype(float)
    base["TeamId"] = pd.to_numeric(base["team"], errors="raise").astype(int)
    if base["Pos"].isna().any():
        bad = (
            base.loc[base["Pos"].isna(), ["ID", "position"]]
            .head(10)
            .to_dict("records")
        )
        raise ValueError(f"unsupported FPL positions in solver export: {bad}")
    if (base["Value"] <= 0).any():
        raise ValueError("sealed solver export contains a non-positive FPL price")

    projections = projections.copy()
    projections["player_id"] = pd.to_numeric(
        projections["player_id"], errors="raise"
    ).astype(int)
    projections["gw"] = pd.to_numeric(projections["gw"], errors="raise").astype(int)
    projections[projection_col] = pd.to_numeric(
        projections[projection_col], errors="coerce"
    )
    if projections[projection_col].isna().any():
        raise ValueError("sealed projection surface contains missing/non-numeric xP")

    gws = [int(gw) for gw in bundle.manifest.get("gameweeks") or []]
    observed = sorted(projections["gw"].unique().tolist())
    if not gws or observed != gws:
        raise ValueError(
            f"sealed projection Gameweeks do not match DecisionBundle: "
            f"bundle={gws} observed={observed}"
        )
    unknown = sorted(set(projections["player_id"]) - set(base["ID"]))
    if unknown:
        raise ValueError(f"projection surface contains unknown player IDs: {unknown[:10]}")

    xp = projections.pivot_table(
        index="player_id",
        columns="gw",
        values=projection_col,
        aggfunc="sum",
        fill_value=0.0,
    )
    fixture_count = projections.groupby(["player_id", "gw"]).size().unstack(fill_value=0)
    expected_minutes = base.set_index("ID")["expected_minutes"].apply(
        pd.to_numeric, errors="coerce"
    ).fillna(0.0)

    out = base[["ID", "Name", "Pos", "Value", "TeamId"]].copy()
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

    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False, float_format="%.4f")
    print(
        f"Exported {len(out)} sealed official-ID players on {projection_col} "
        f"for GW={gws} from bundle={bundle.bundle_id} to {output}"
    )
