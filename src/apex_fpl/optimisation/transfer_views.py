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
    required_ids: set[int] | None = None,
) -> set[int]:
    """Build a loss-resistant transfer candidate universe.

    A simple global top-N xP cut can silently remove goalkeepers, defenders or cheap
    enablers because premium attackers naturally dominate absolute xP. Pinnacle
    preserves the current/required squad, positional leaders, price-band leaders,
    each position's price/xP Pareto frontier and short-term Gameweek punts.

    Discretionary candidates must have at least one projection row in the requested
    horizon. This avoids spending a bounded pool on zero-row players that the exact
    transfer MILP would immediately discard when it builds its projection matrix.
    """
    d = players.drop_duplicates("player_id").copy()
    d = d[d["position"].isin(SQUAD_COUNTS)].copy()
    px = projections[projections["gw"].isin(gameweeks)][
        ["player_id", "gw", projection_col]
    ].copy()
    px[projection_col] = pd.to_numeric(
        px[projection_col], errors="coerce"
    ).fillna(0.0)
    projected_ids = set(px["player_id"].dropna().astype(int))
    horizon = px.groupby("player_id")[projection_col].sum()
    d["_plan_xp"] = d["player_id"].map(horizon).fillna(0.0)
    d["_price"] = pd.to_numeric(d["price"], errors="coerce").fillna(99.0)
    d["_price_band"] = (d["_price"] * 2.0).round() / 2.0

    required = set(map(int, current_squad)) | set(map(int, required_ids or set()))
    keep: set[int] = set(required)
    per_position = max(
        18, int(math.ceil(target_size / max(len(SQUAD_COUNTS), 1)))
    )
    for pos in SQUAD_COUNTS:
        # The MILP can only use players represented on the requested projection
        # horizon. Preserve required IDs separately above, but fill the bounded
        # discretionary pool from candidates that will survive that downstream
        # projection-matrix filter.
        part = d[
            (d["position"] == pos)
            & d["player_id"].astype(int).isin(projected_ids)
        ].copy()
        if part.empty:
            continue
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

    A bounded-pool failure is not proof of mathematical infeasibility. When the
    loss-resistant bounded solve is non-optimal, retry exactly once on the complete
    usable player/projection universe. Only the full solve may therefore return the
    final non-optimal status to callers such as the joint launch planner.
    """
    if projection_col not in projections.columns:
        if projection_col == "xp" and "risk_adjusted_xp" in projections.columns:
            projection_col = "risk_adjusted_xp"
        else:
            raise ValueError(f"projection column not found: {projection_col}")

    full_view = projections.copy()
    full_view["risk_adjusted_xp"] = pd.to_numeric(
        full_view[projection_col], errors="coerce"
    ).fillna(0.0)
    player_view = players
    view = full_view
    effective_limit = int(candidate_limit)
    if pinnacle_pool:
        required_ids = set(map(int, current_squad))
        required_ids.update(map(int, kwargs.get("locked") or set()))
        ids = _pinnacle_candidate_ids(
            players,
            full_view,
            gameweeks,
            current_squad,
            projection_col="risk_adjusted_xp",
            target_size=candidate_limit,
            required_ids=required_ids,
        )
        player_view = players[
            players["player_id"].astype(int).isin(ids)
        ].copy()
        view = full_view[full_view["player_id"].astype(int).isin(ids)].copy()
        # The candidate IDs above are already the canonical loss-resistant pool.
        # Prevent the lower-level solver's compatibility top-xP limit from pruning
        # that prefiltered universe a second time.
        effective_limit = max(len(player_view), effective_limit)

    bounded = optimise_transfer_plan(
        player_view,
        view,
        gameweeks,
        current_squad,
        candidate_limit=effective_limit,
        **kwargs,
    )
    if bounded.status == "Optimal" or not pinnacle_pool:
        return bounded

    # A lossy bounded universe can make an otherwise feasible transfer path appear
    # infeasible. Retry once with every player and every projection row. Setting the
    # lower-level limit to the full distinct-player count makes its legacy top-xP
    # compatibility cut a no-op, while all exact FPL legality constraints remain.
    full_limit = max(
        int(candidate_limit),
        int(players.drop_duplicates("player_id").shape[0]),
    )
    bounded_ids = set(player_view["player_id"].astype(int))
    full_ids = set(players["player_id"].astype(int))
    if bounded_ids == full_ids:
        return bounded
    return optimise_transfer_plan(
        players,
        full_view,
        gameweeks,
        current_squad,
        candidate_limit=full_limit,
        **kwargs,
    )
