from __future__ import annotations

import math

import pandas as pd

from apex_fpl.constants import SQUAD_COUNTS
from apex_fpl.optimisation.initial_transfer_path import optimise_initial_transfer_path
from apex_fpl.optimisation.transfers import TransferPlan, optimise_transfer_plan


def _pinnacle_candidate_ids(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    current_squad: set[int],
    *,
    projection_col: str,
    target_size: int = 180,
) -> set[int]:
    """Build a loss-resistant transfer candidate universe.

    A simple global top-N xP cut can silently remove goalkeepers, defenders or cheap
    enablers because premium attackers naturally dominate absolute xP. Pinnacle
    preserves the current squad, positional leaders, price-band leaders, each
    position's price/xP Pareto frontier and short-term Gameweek punts.
    """
    d = players.drop_duplicates("player_id").copy()
    d = d[d["position"].isin(SQUAD_COUNTS)].copy()
    px = projections[projections["gw"].isin(gameweeks)][
        ["player_id", "gw", projection_col]
    ].copy()
    px[projection_col] = pd.to_numeric(
        px[projection_col], errors="coerce"
    ).fillna(0.0)
    horizon = px.groupby("player_id")[projection_col].sum()
    d["_plan_xp"] = d["player_id"].map(horizon).fillna(0.0)
    d["_price"] = pd.to_numeric(d["price"], errors="coerce").fillna(99.0)
    d["_price_band"] = (d["_price"] * 2.0).round() / 2.0

    keep: set[int] = set(map(int, current_squad))
    per_position = max(
        18, int(math.ceil(target_size / max(len(SQUAD_COUNTS), 1)))
    )
    for pos in SQUAD_COUNTS:
        part = d[d["position"] == pos].copy()
        keep.update(
            part.nlargest(per_position, "_plan_xp")["player_id"].astype(int)
        )

        for _, band in part.groupby("_price_band"):
            keep.update(band.nlargest(4, "_plan_xp")["player_id"].astype(int))

        frontier = part.sort_values(
            ["_price", "_plan_xp"], ascending=[True, False]
        )
        best = float("-inf")
        for _, row in frontier.iterrows():
            value = float(row["_plan_xp"])
            if value > best + 1e-9:
                keep.add(int(row["player_id"]))
                best = value

        for gw in gameweeks:
            gw_values = (
                px[px["gw"] == int(gw)]
                .groupby("player_id")[projection_col]
                .sum()
            )
            gw_part = part[["player_id"]].copy()
            gw_part["_gw"] = gw_part["player_id"].map(gw_values).fillna(0.0)
            keep.update(gw_part.nlargest(10, "_gw")["player_id"].astype(int))

    return keep


def _projection_view(
    projections: pd.DataFrame,
    projection_col: str,
) -> tuple[pd.DataFrame, str]:
    if projection_col not in projections.columns:
        if projection_col == "xp" and "risk_adjusted_xp" in projections.columns:
            projection_col = "risk_adjusted_xp"
        else:
            raise ValueError(f"projection column not found: {projection_col}")
    view = projections.copy()
    view["risk_adjusted_xp"] = pd.to_numeric(
        view[projection_col], errors="coerce"
    ).fillna(0.0)
    return view, projection_col


def optimise_transfer_plan_view(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    current_squad: set[int],
    *,
    projection_col: str = "xp",
    pinnacle_pool: bool = True,
    candidate_limit: int = 180,
    **kwargs,
) -> TransferPlan:
    """Run the exact transfer MILP on an explicit projection surface.

    By default Pinnacle uses ensemble mean ``xp`` and a position/price-aware
    candidate universe. The legacy risk-adjusted surface remains available
    explicitly. The underlying transfer constraints are unchanged.
    """
    view, projection_col = _projection_view(projections, projection_col)
    player_view = players
    effective_limit = int(candidate_limit)
    if pinnacle_pool:
        ids = _pinnacle_candidate_ids(
            players,
            view,
            gameweeks,
            current_squad,
            projection_col="risk_adjusted_xp",
            target_size=candidate_limit,
        )
        player_view = players[
            players["player_id"].astype(int).isin(ids)
        ].copy()
        view = view[view["player_id"].astype(int).isin(ids)].copy()
        effective_limit = max(len(player_view), effective_limit)

    return optimise_transfer_plan(
        player_view,
        view,
        gameweeks,
        current_squad,
        candidate_limit=effective_limit,
        **kwargs,
    )


def optimise_initial_transfer_plan_view(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    *,
    projection_col: str = "xp",
    candidate_limit: int = 180,
    budget: float = 100.0,
    excluded_initial_squads: list[set[int]] | None = None,
    **kwargs,
) -> TransferPlan:
    """Optimise a free GW1 squad and legal future transfer path on one xP surface.

    The candidate universe is position/price aware and does not inherit any static
    starting squad. This is the correct pre-GW1 state transition: select the first
    15 freely under budget, then begin GW2 with one free transfer.
    """
    view, projection_col = _projection_view(projections, projection_col)
    ids = _pinnacle_candidate_ids(
        players,
        view,
        gameweeks,
        set(),
        projection_col="risk_adjusted_xp",
        target_size=candidate_limit,
    )
    player_view = players[players["player_id"].astype(int).isin(ids)].copy()
    view = view[view["player_id"].astype(int).isin(ids)].copy()
    return optimise_initial_transfer_path(
        player_view,
        view,
        gameweeks,
        budget=budget,
        projection_col="risk_adjusted_xp",
        excluded_initial_squads=excluded_initial_squads,
        **kwargs,
    )
