from __future__ import annotations

import math

import pandas as pd

from apex_fpl.constants import SQUAD_COUNTS
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
    instead preserves multiple complementary candidate classes:

    - the current squad;
    - top horizon xP within every FPL position;
    - top assets inside every £0.5m price band/position;
    - each position's price/xP Pareto frontier;
    - top short-term punts by position in every individual Gameweek.

    The resulting pool stays computationally manageable while being materially less
    likely to prune the true budget-constrained optimum.
    """
    d = players.drop_duplicates("player_id").copy()
    d = d[d["position"].isin(SQUAD_COUNTS)].copy()
    value_col = projection_col
    px = projections[projections["gw"].isin(gameweeks)][
        ["player_id", "gw", value_col]
    ].copy()
    px[value_col] = pd.to_numeric(px[value_col], errors="coerce").fillna(0.0)
    horizon = px.groupby("player_id")[value_col].sum()
    d["_plan_xp"] = d["player_id"].map(horizon).fillna(0.0)
    d["_price"] = pd.to_numeric(d["price"], errors="coerce").fillna(99.0)
    d["_price_band"] = (d["_price"] * 2.0).round() / 2.0

    keep: set[int] = set(map(int, current_squad))
    per_position = max(18, int(math.ceil(target_size / max(len(SQUAD_COUNTS), 1))))
    for pos in SQUAD_COUNTS:
        part = d[d["position"] == pos].copy()
        keep.update(part.nlargest(per_position, "_plan_xp")["player_id"].astype(int))

        # Budget enablers / same-price alternatives.
        for _, band in part.groupby("_price_band"):
            keep.update(band.nlargest(4, "_plan_xp")["player_id"].astype(int))

        # Pareto frontier: not dominated by a cheaper player with at least as much xP.
        frontier = part.sort_values(["_price", "_plan_xp"], ascending=[True, False])
        best = float("-inf")
        for row in frontier.itertuples(index=False):
            value = float(row._plan_xp)
            if value > best + 1e-9:
                keep.add(int(row.player_id))
                best = value

        # One-week upside can be hidden by a horizon aggregate.
        for gw in gameweeks:
            gw_values = px[px["gw"] == int(gw)].groupby("player_id")[value_col].sum()
            gw_part = part[["player_id"]].copy()
            gw_part["_gw"] = gw_part["player_id"].map(gw_values).fillna(0.0)
            keep.update(gw_part.nlargest(10, "_gw")["player_id"].astype(int))

    return keep


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
    if projection_col not in projections.columns:
        if projection_col == "xp" and "risk_adjusted_xp" in projections.columns:
            projection_col = "risk_adjusted_xp"
        else:
            raise ValueError(f"projection column not found: {projection_col}")

    view = projections.copy()
    view["risk_adjusted_xp"] = pd.to_numeric(
        view[projection_col], errors="coerce"
    ).fillna(0.0)
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
        player_view = players[players["player_id"].astype(int).isin(ids)].copy()
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
