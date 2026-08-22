from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from apex_fpl.constants import SQUAD_COUNTS, XI_MAX, XI_MIN
from apex_fpl.optimisation.solver_status import scipy_milp_metadata, scipy_milp_status


@dataclass
class SquadSolution:
    status: str
    objective: float
    squad: pd.DataFrame
    xi: pd.DataFrame
    captain: pd.DataFrame
    vice_captain: pd.DataFrame
    bench: pd.DataFrame
    solver: dict = field(default_factory=dict)


def optimise_squad(
    players: pd.DataFrame,
    budget: float = 100.0,
    max_per_team: int = 3,
    locked: set[int] | None = None,
    banned: set[int] | None = None,
) -> SquadSolution:
    """Solve the legal FPL 15-player squad, XI, captain and bench as a MILP.

    Solver termination is non-lossy. Only a real HiGHS status code 2 is reported
    as mathematical infeasibility; input errors and solver limits remain distinct.
    """
    locked, banned = locked or set(), banned or set()
    d = players.drop_duplicates("player_id").copy()
    d = d[d["position"].isin(SQUAD_COUNTS)].reset_index(drop=True)
    n = len(d)
    if n == 0:
        empty = d.iloc[0:0]
        return SquadSolution(
            "InputError",
            float("nan"),
            empty,
            empty,
            empty,
            empty,
            empty,
            {"status_code": None, "termination_reason": "no eligible players"},
        )

    def s(i: int) -> int:
        return i

    def x(i: int) -> int:
        return n + i

    def c(i: int) -> int:
        return 2 * n + i

    utility_col = (
        "discounted_horizon_utility"
        if "discounted_horizon_utility" in d.columns
        else "horizon_xp"
    )
    horizon = pd.to_numeric(d[utility_col], errors="coerce").fillna(0).to_numpy(float)
    gw1 = (
        pd.to_numeric(d.get("gw1_xp", d["horizon_xp"]), errors="coerce")
        .fillna(0)
        .to_numpy(float)
    )
    objective = np.zeros(3 * n)
    objective[:n] = 0.18 * horizon
    objective[n : 2 * n] = gw1
    objective[2 * n : 3 * n] = gw1
    cvec = -objective

    rows: list[dict[int, float]] = []
    lower: list[float] = []
    upper: list[float] = []

    def add(coeffs: dict[int, float], lo: float, hi: float):
        rows.append(coeffs)
        lower.append(lo)
        upper.append(hi)

    add({s(i): 1 for i in range(n)}, 15, 15)
    add({x(i): 1 for i in range(n)}, 11, 11)
    add({c(i): 1 for i in range(n)}, 1, 1)
    add({s(i): float(d.loc[i, "price"]) for i in range(n)}, -np.inf, budget)

    for pos, count in SQUAD_COUNTS.items():
        idx = [i for i in range(n) if d.loc[i, "position"] == pos]
        add({s(i): 1 for i in idx}, count, count)
        add({x(i): 1 for i in idx}, XI_MIN[pos], XI_MAX[pos])

    for team in d["team"].dropna().unique():
        idx = [i for i in range(n) if d.loc[i, "team"] == team]
        add({s(i): 1 for i in idx}, -np.inf, max_per_team)

    for i in range(n):
        add({x(i): 1, s(i): -1}, -np.inf, 0)
        add({c(i): 1, x(i): -1}, -np.inf, 0)

    A = lil_matrix((len(rows), 3 * n), dtype=float)
    for r, coeffs in enumerate(rows):
        for col, val in coeffs.items():
            A[r, col] = val

    lb = np.zeros(3 * n)
    ub = np.ones(3 * n)
    by_id = {int(d.loc[i, "player_id"]): i for i in range(n)}
    for pid in locked:
        if pid in by_id:
            lb[s(by_id[pid])] = 1
    for pid in banned:
        if pid in by_id:
            ub[s(by_id[pid])] = 0

    time_limit = 60
    res = milp(
        c=cvec,
        integrality=np.ones(3 * n),
        bounds=Bounds(lb, ub),
        constraints=LinearConstraint(A.tocsr(), np.array(lower), np.array(upper)),
        options={"time_limit": time_limit},
    )
    solver = scipy_milp_metadata(res, time_limit=time_limit)
    status = scipy_milp_status(res)
    if status != "Optimal":
        empty = d.iloc[0:0]
        return SquadSolution(
            status,
            float("nan"),
            empty,
            empty,
            empty,
            empty,
            empty,
            solver,
        )

    sol = res.x
    chosen = [i for i in range(n) if sol[s(i)] > 0.5]
    lineup = [i for i in range(n) if sol[x(i)] > 0.5]
    capt = [i for i in range(n) if sol[c(i)] > 0.5]
    benched = [i for i in chosen if i not in lineup]
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
        "raw_horizon_xp",
        "discounted_horizon_utility",
        "horizon_xp",
        "fixture_decay",
        "projection_confidence",
    ]
    cols = [col for col in detail_columns if col in d.columns]
    squad_df = d.loc[chosen, cols].sort_values(
        ["position", "horizon_xp"], ascending=[True, False]
    )
    xi_df = d.loc[lineup, cols].sort_values("gw1_xp", ascending=False)
    cap_df = d.loc[capt, cols]
    captain_idx = capt[0] if capt else None
    vice_pool = [i for i in lineup if i != captain_idx]
    if vice_pool:
        appearance_prob = pd.to_numeric(
            d.get("appearance_probability", pd.Series(1.0, index=d.index)),
            errors="coerce",
        ).fillna(1.0)
        vice_score = {
            i: float(gw1[i]) * float(appearance_prob.iloc[i]) for i in vice_pool
        }
        vice_idx = max(vice_pool, key=lambda i: vice_score[i])
        vice_df = d.loc[[vice_idx], cols]
    else:
        vice_df = d.iloc[0:0][cols]
    bench_df = d.loc[benched, cols].sort_values("gw1_xp", ascending=False)
    return SquadSolution(
        "Optimal",
        float(-res.fun),
        squad_df,
        xi_df,
        cap_df,
        vice_df,
        bench_df,
        solver,
    )
