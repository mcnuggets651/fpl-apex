from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from apex_fpl.constants import SQUAD_COUNTS, XI_MAX, XI_MIN
from apex_fpl.models.scenarios import ProjectionScenarios


@dataclass
class RobustSquadSolution:
    status: str
    objective: float
    mean_points: float
    lower_tail_cvar: float
    cvar_alpha: float
    cvar_weight: float
    squad: pd.DataFrame
    xi: pd.DataFrame
    captain: pd.DataFrame
    vice_captain: pd.DataFrame
    bench: pd.DataFrame
    scenario_scores: np.ndarray


def optimise_initial_cvar(
    players: pd.DataFrame,
    scenarios: ProjectionScenarios,
    *,
    budget: float = 100.0,
    max_per_team: int = 3,
    decay: float = 0.90,
    bench_weight: float = 0.08,
    cvar_alpha: float = 0.10,
    cvar_weight: float = 0.20,
    locked: set[int] | None = None,
    banned: set[int] | None = None,
) -> RobustSquadSolution:
    """Solve a legal initial FPL squad against correlated forecast scenarios.

    The objective is a convex blend of expected horizon points and lower-tail
    Conditional Value at Risk (CVaR):

        (1-lambda) E[V] + lambda CVaR_alpha(V)

    where ``V`` is total discounted squad/lineup/captain value across the horizon.
    One squad, XI and captain decision is used across all scenarios for each GW,
    so the optimiser does not receive impossible perfect foresight.
    """
    locked, banned = set(locked or set()), set(banned or set())
    alpha = float(cvar_alpha)
    risk_weight = float(cvar_weight)
    if not 0.01 <= alpha <= 0.50:
        raise ValueError("cvar_alpha must be between 0.01 and 0.50")
    if not 0.0 <= risk_weight <= 1.0:
        raise ValueError("cvar_weight must be between 0 and 1")

    d = players.drop_duplicates("player_id").copy()
    d = d[d["position"].isin(SQUAD_COUNTS)].reset_index(drop=True)
    pids = d["player_id"].astype(int).tolist()
    if not pids:
        empty = d.iloc[0:0]
        return RobustSquadSolution(
            "Infeasible", math.nan, math.nan, math.nan, alpha, risk_weight,
            empty, empty, empty, empty, empty, np.asarray([], dtype=float),
        )

    scenario_pid_index = {int(pid): i for i, pid in enumerate(scenarios.player_ids)}
    missing = [pid for pid in pids if pid not in scenario_pid_index]
    if missing:
        raise ValueError(f"scenario surface missing player IDs: {missing[:10]}")

    n = len(d)
    t_count = len(scenarios.gameweeks)
    s_count = scenarios.n_scenarios
    values = np.zeros((s_count, n, t_count), dtype=float)
    for i, pid in enumerate(pids):
        values[:, i, :] = scenarios.values[:, scenario_pid_index[pid], :]

    # Binary variables: squad, XI by GW, captain by GW.
    S0 = 0
    X0 = n
    C0 = n + n * t_count
    binary_count = n + 2 * n * t_count
    # Continuous CVaR variables: eta and shortfall u_s.
    ETA = binary_count
    U0 = ETA + 1
    total_vars = binary_count + 1 + s_count

    def sv(i: int) -> int:
        return S0 + i

    def xv(i: int, t: int) -> int:
        return X0 + t * n + i

    def cv(i: int, t: int) -> int:
        return C0 + t * n + i

    def uv(s: int) -> int:
        return U0 + s

    bw = float(np.clip(bench_weight, 0.0, 0.35))
    discounts = np.asarray([float(decay) ** t for t in range(t_count)], dtype=float)
    mean_values = np.mean(values, axis=0)

    # Maximise objective, while scipy.milp minimises.
    maximise = np.zeros(total_vars, dtype=float)
    mean_scale = 1.0 - risk_weight
    for t in range(t_count):
        disc = discounts[t]
        for i in range(n):
            value = max(float(mean_values[i, t]), 0.0) * disc
            maximise[sv(i)] += mean_scale * bw * value
            maximise[xv(i, t)] += mean_scale * (1.0 - bw) * value
            maximise[cv(i, t)] += mean_scale * value
    maximise[ETA] += risk_weight
    shortfall_weight = risk_weight / (alpha * s_count)
    for s in range(s_count):
        maximise[uv(s)] -= shortfall_weight

    rows: list[dict[int, float]] = []
    lower: list[float] = []
    upper: list[float] = []

    def add(coeffs: dict[int, float], lo: float, hi: float) -> None:
        rows.append(coeffs)
        lower.append(lo)
        upper.append(hi)

    add({sv(i): 1.0 for i in range(n)}, 15, 15)
    add(
        {sv(i): float(d.loc[i, "price"]) for i in range(n)},
        -np.inf,
        float(budget),
    )
    for pos, count in SQUAD_COUNTS.items():
        idx = [i for i in range(n) if d.loc[i, "position"] == pos]
        add({sv(i): 1.0 for i in idx}, count, count)
    for team in d["team"].dropna().unique():
        idx = [i for i in range(n) if d.loc[i, "team"] == team]
        add({sv(i): 1.0 for i in idx}, -np.inf, max_per_team)

    for t in range(t_count):
        add({xv(i, t): 1.0 for i in range(n)}, 11, 11)
        add({cv(i, t): 1.0 for i in range(n)}, 1, 1)
        for pos in SQUAD_COUNTS:
            idx = [i for i in range(n) if d.loc[i, "position"] == pos]
            add({xv(i, t): 1.0 for i in idx}, XI_MIN[pos], XI_MAX[pos])
        for i in range(n):
            add({xv(i, t): 1.0, sv(i): -1.0}, -np.inf, 0)
            add({cv(i, t): 1.0, xv(i, t): -1.0}, -np.inf, 0)

    # u_s >= eta - V_s  =>  eta - V_s - u_s <= 0.
    for scenario_idx in range(s_count):
        coeffs: dict[int, float] = {ETA: 1.0, uv(scenario_idx): -1.0}
        for t in range(t_count):
            disc = discounts[t]
            for i in range(n):
                value = max(float(values[scenario_idx, i, t]), 0.0) * disc
                if value == 0.0:
                    continue
                coeffs[sv(i)] = coeffs.get(sv(i), 0.0) - bw * value
                coeffs[xv(i, t)] = coeffs.get(xv(i, t), 0.0) - (1.0 - bw) * value
                coeffs[cv(i, t)] = coeffs.get(cv(i, t), 0.0) - value
        add(coeffs, -np.inf, 0.0)

    A = lil_matrix((len(rows), total_vars), dtype=float)
    for r, coeffs in enumerate(rows):
        for col, value in coeffs.items():
            A[r, col] = value

    lb = np.zeros(total_vars, dtype=float)
    ub = np.ones(total_vars, dtype=float)
    integrality = np.ones(total_vars, dtype=int)
    # CVaR eta can be negative in principle; FPL projected totals normally are not,
    # but a broad lower bound keeps the formulation mathematically complete.
    lb[ETA], ub[ETA], integrality[ETA] = -1000.0, 3000.0, 0
    for s in range(s_count):
        lb[uv(s)], ub[uv(s)], integrality[uv(s)] = 0.0, 5000.0, 0

    by_id = {pid: i for i, pid in enumerate(pids)}
    for pid in locked:
        if int(pid) in by_id:
            lb[sv(by_id[int(pid)])] = 1.0
    for pid in banned:
        if int(pid) in by_id:
            ub[sv(by_id[int(pid)])] = 0.0

    result = milp(
        c=-maximise,
        integrality=integrality,
        bounds=Bounds(lb, ub),
        constraints=LinearConstraint(
            A.tocsr(),
            np.asarray(lower, dtype=float),
            np.asarray(upper, dtype=float),
        ),
        options={"time_limit": 180, "mip_rel_gap": 0.002},
    )
    if not result.success or result.x is None:
        empty = d.iloc[0:0]
        return RobustSquadSolution(
            "Infeasible", math.nan, math.nan, math.nan, alpha, risk_weight,
            empty, empty, empty, empty, empty, np.asarray([], dtype=float),
        )

    sol = result.x
    chosen = [i for i in range(n) if sol[sv(i)] > 0.5]
    lineup = [i for i in range(n) if sol[xv(i, 0)] > 0.5]
    capt = [i for i in range(n) if sol[cv(i, 0)] > 0.5]
    benched = [i for i in chosen if i not in lineup]

    scenario_scores = np.zeros(s_count, dtype=float)
    for s in range(s_count):
        score = 0.0
        for t in range(t_count):
            disc = discounts[t]
            for i in chosen:
                score += bw * values[s, i, t] * disc
            for i in range(n):
                if sol[xv(i, t)] > 0.5:
                    score += (1.0 - bw) * values[s, i, t] * disc
                if sol[cv(i, t)] > 0.5:
                    score += values[s, i, t] * disc
        scenario_scores[s] = score

    mean_points = float(np.mean(scenario_scores))
    tail_count = max(1, int(math.ceil(alpha * s_count)))
    lower_cvar = float(np.mean(np.sort(scenario_scores)[:tail_count]))
    blended = (1.0 - risk_weight) * mean_points + risk_weight * lower_cvar

    gw1_mean = np.mean(values[:, :, 0], axis=0)
    d["_robust_gw1_xp"] = gw1_mean
    if "gw1_xp" not in d.columns:
        d["gw1_xp"] = d["_robust_gw1_xp"]
    details = [
        "player_id", "web_name", "team_name", "position", "price",
        "expected_minutes", "start_probability", "appearance_probability",
        "tactical_role", "tactical_role_source", "role_confidence",
        "gw1_xp", "xpts_3", "xpts_5", "xpts_8", "horizon_xp",
        "projection_confidence",
    ]
    cols = [col for col in details if col in d.columns]
    sort_horizon = "horizon_xp" if "horizon_xp" in cols else "gw1_xp"
    squad_df = d.loc[chosen, cols].sort_values(
        ["position", sort_horizon], ascending=[True, False]
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
            key=lambda i: float(gw1_mean[i]) * float(appearance.iloc[i]),
        )
        vice_df = d.loc[[vice_idx], cols]
    else:
        vice_df = d.iloc[0:0][cols]
    bench_df = d.loc[benched, cols].sort_values("gw1_xp", ascending=False)

    return RobustSquadSolution(
        status="Optimal",
        objective=blended,
        mean_points=mean_points,
        lower_tail_cvar=lower_cvar,
        cvar_alpha=alpha,
        cvar_weight=risk_weight,
        squad=squad_df,
        xi=xi_df,
        captain=cap_df,
        vice_captain=vice_df,
        bench=bench_df,
        scenario_scores=scenario_scores,
    )
