from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from apex_fpl.constants import SQUAD_COUNTS, XI_MAX, XI_MIN
from apex_fpl.optimisation.squad import SquadSolution


def optimise_initial_horizon(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    budget: float = 100.0,
    max_per_team: int = 3,
    decay: float = 0.90,
    bench_weight: float = 0.08,
    locked: set[int] | None = None,
    banned: set[int] | None = None,
    projection_col: str = "xp",
) -> SquadSolution:
    """Optimise the initial squad over the complete planning horizon.

    The 15-player squad is fixed while XI and captain are re-optimised independently
    for every Gameweek. By default the objective uses the ensemble mean ``xp`` so
    this is a genuine maximum-expected-points baseline. Risk belongs in the separate
    correlated CVaR layer rather than being silently double-counted here.

    ``risk_adjusted_xp`` remains a supported explicit projection column and is the
    fallback for older/test projection tables that do not contain ``xp``.
    ``bench_weight`` is only a first-stage reserve-value proxy; the final published
    GW mechanics are recalculated with exact captain/vice and autosub expectation.
    """
    locked, banned = locked or set(), banned or set()
    gws = [int(gw) for gw in gameweeks]
    if not gws:
        empty = players.iloc[0:0].copy()
        return SquadSolution("Infeasible", float("nan"), empty, empty, empty, empty, empty)

    d = players.drop_duplicates("player_id").copy()
    d = d[d["position"].isin(SQUAD_COUNTS)].reset_index(drop=True)
    if d.empty:
        empty = d.iloc[0:0]
        return SquadSolution("Infeasible", float("nan"), empty, empty, empty, empty, empty)

    club_col = "team" if "team" in d.columns else "team_name"
    if club_col not in d.columns:
        raise ValueError("players require team or team_name for club constraints")

    value_col = projection_col if projection_col in projections.columns else "risk_adjusted_xp"
    if value_col not in projections.columns:
        raise ValueError(
            f"projection table requires {projection_col!r} or 'risk_adjusted_xp'"
        )
    px = projections[projections["gw"].isin(gws)][
        ["player_id", "gw", value_col]
    ].copy()
    matrix = px.pivot_table(
        index="player_id",
        columns="gw",
        values=value_col,
        aggfunc="sum",
        fill_value=0.0,
    )
    for gw in gws:
        if gw not in matrix.columns:
            matrix[gw] = 0.0

    n, t_count = len(d), len(gws)
    pids = d["player_id"].astype(int).tolist()
    xp = np.zeros((n, t_count), dtype=float)
    for i, pid in enumerate(pids):
        if pid in matrix.index:
            xp[i, :] = [float(matrix.loc[pid, gw]) for gw in gws]

    # Variables: fixed squad S_i; per-GW XI X_i,t; per-GW captain C_i,t.
    S0 = 0
    X0 = n
    C0 = n + n * t_count
    total_vars = n + 2 * n * t_count

    def s(i: int) -> int:
        return S0 + i

    def x(i: int, t: int) -> int:
        return X0 + t * n + i

    def c(i: int, t: int) -> int:
        return C0 + t * n + i

    bw = float(np.clip(bench_weight, 0.0, 0.35))
    objective = np.zeros(total_vars, dtype=float)
    for t in range(t_count):
        discount = float(decay) ** t
        for i in range(n):
            value = max(float(xp[i, t]), 0.0) * discount
            objective[s(i)] += bw * value
            objective[x(i, t)] += (1.0 - bw) * value
            # Normal captaincy is one additional copy of expected points.
            objective[c(i, t)] += value

    rows: list[dict[int, float]] = []
    lower: list[float] = []
    upper: list[float] = []

    def add(coeffs: dict[int, float], lo: float, hi: float) -> None:
        rows.append(coeffs)
        lower.append(lo)
        upper.append(hi)

    add({s(i): 1.0 for i in range(n)}, 15, 15)
    add(
        {s(i): float(d.loc[i, "price"]) for i in range(n)},
        -np.inf,
        float(budget),
    )

    for pos, count in SQUAD_COUNTS.items():
        idx = [i for i in range(n) if d.loc[i, "position"] == pos]
        add({s(i): 1.0 for i in idx}, count, count)

    for team in d[club_col].dropna().unique():
        idx = [i for i in range(n) if d.loc[i, club_col] == team]
        add({s(i): 1.0 for i in idx}, -np.inf, max_per_team)

    for t in range(t_count):
        add({x(i, t): 1.0 for i in range(n)}, 11, 11)
        add({c(i, t): 1.0 for i in range(n)}, 1, 1)
        for pos in SQUAD_COUNTS:
            idx = [i for i in range(n) if d.loc[i, "position"] == pos]
            add({x(i, t): 1.0 for i in idx}, XI_MIN[pos], XI_MAX[pos])
        for i in range(n):
            add({x(i, t): 1.0, s(i): -1.0}, -np.inf, 0)
            add({c(i, t): 1.0, x(i, t): -1.0}, -np.inf, 0)

    A = lil_matrix((len(rows), total_vars), dtype=float)
    for r, coeffs in enumerate(rows):
        for col, value in coeffs.items():
            A[r, col] = value

    lb = np.zeros(total_vars, dtype=float)
    ub = np.ones(total_vars, dtype=float)
    by_id = {pid: i for i, pid in enumerate(pids)}
    for pid in locked:
        if int(pid) in by_id:
            lb[s(by_id[int(pid)])] = 1.0
    for pid in banned:
        if int(pid) in by_id:
            ub[s(by_id[int(pid)])] = 0.0

    result = milp(
        c=-objective,
        integrality=np.ones(total_vars, dtype=int),
        bounds=Bounds(lb, ub),
        constraints=LinearConstraint(
            A.tocsr(),
            np.asarray(lower, dtype=float),
            np.asarray(upper, dtype=float),
        ),
        options={"time_limit": 90, "mip_rel_gap": 0.001},
    )
    if not result.success or result.x is None:
        empty = d.iloc[0:0]
        return SquadSolution("Infeasible", float("nan"), empty, empty, empty, empty, empty)

    sol = result.x
    chosen = [i for i in range(n) if sol[s(i)] > 0.5]
    lineup = [i for i in range(n) if sol[x(i, 0)] > 0.5]
    capt = [i for i in range(n) if sol[c(i, 0)] > 0.5]
    benched = [i for i in chosen if i not in lineup]

    # Output GW1 xP must describe the same surface the optimiser solved, otherwise
    # a risk-adjusted display column can misleadingly disagree with the EV decision.
    gw1_map = {pid: float(xp[i, 0]) for i, pid in enumerate(pids)}
    d["gw1_xp"] = d["player_id"].map(gw1_map).fillna(0.0)
    d["decision_projection_col"] = value_col

    detail_columns = [
        "player_id",
        "web_name",
        "team_name",
        "position",
        "price",
        "expected_minutes",
        "start_probability",
        "appearance_probability",
        "tactical_role",
        "tactical_role_source",
        "role_confidence",
        "gw1_xp",
        "xpts_3",
        "xpts_5",
        "xpts_8",
        "horizon_xp",
        "projection_confidence",
        "decision_projection_col",
    ]
    cols = [col for col in detail_columns if col in d.columns]
    squad_df = d.loc[chosen, cols].sort_values(
        ["position", "horizon_xp" if "horizon_xp" in cols else "gw1_xp"],
        ascending=[True, False],
    )
    xi_df = d.loc[lineup, cols].sort_values("gw1_xp", ascending=False)
    cap_df = d.loc[capt, cols]

    captain_idx = capt[0] if capt else None
    vice_pool = [i for i in lineup if i != captain_idx]
    if vice_pool:
        appearance = pd.to_numeric(
            d.get("appearance_probability", pd.Series(1.0, index=d.index)),
            errors="coerce",
        ).fillna(1.0)
        vice_idx = max(
            vice_pool,
            key=lambda i: float(xp[i, 0]) * float(appearance.iloc[i]),
        )
        vice_df = d.loc[[vice_idx], cols]
    else:
        vice_df = d.iloc[0:0][cols]

    bench_df = d.loc[benched, cols].sort_values("gw1_xp", ascending=False)
    return SquadSolution(
        "Optimal",
        float(-result.fun),
        squad_df,
        xi_df,
        cap_df,
        vice_df,
        bench_df,
    )
