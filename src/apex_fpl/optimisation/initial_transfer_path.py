from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from apex_fpl.constants import SQUAD_COUNTS, XI_MAX, XI_MIN
from apex_fpl.optimisation.transfers import TransferPlan, _next_ft
from apex_fpl.rules import MAX_ROLLED_FREE_TRANSFERS, TRANSFER_HIT_COST


def optimise_initial_transfer_path(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    *,
    budget: float = 100.0,
    max_per_team: int = 3,
    decay: float = 0.90,
    projection_col: str = "xp",
    locked: set[int] | None = None,
    banned: set[int] | None = None,
    captain_eligible: set[int] | None = None,
    xi_eligible: set[int] | None = None,
    excluded_initial_squads: list[set[int]] | None = None,
    solver_relative_gap: float = 0.002,
    solver_time_limit: int = 120,
) -> TransferPlan:
    """Jointly choose the GW1 squad and its legal future transfer path.

    GW1 is a free initial selection under the FPL budget rather than a transfer
    window. From GW2 onward the model uses the normal rolled-free-transfer state,
    bank conservation and explicit -4 hit costs. Current official prices are held
    fixed across the planning horizon; future price changes are not forecast.

    The objective deliberately matches the transfer MILP approximation used by
    ``optimise_transfer_plan``. Callers that publish a decision should use this as
    a path/candidate generator and rescore the initial squad with exact GW1
    mechanics before comparing candidates.
    """
    gws = [int(gw) for gw in gameweeks]
    if not gws:
        return TransferPlan("Infeasible", float("nan"), [])

    locked = {int(pid) for pid in (locked or set())}
    banned = {int(pid) for pid in (banned or set())}
    excluded_initial_squads = [
        {int(pid) for pid in squad} for squad in (excluded_initial_squads or [])
    ]
    captain_eligible = (
        None if captain_eligible is None else {int(pid) for pid in captain_eligible}
    )
    if xi_eligible is None and "xi_evidence_eligible" in players:
        xi_eligible = set(
            players.loc[
                players["xi_evidence_eligible"].fillna(False), "player_id"
            ].astype(int)
        )
    xi_eligible = None if xi_eligible is None else {int(pid) for pid in xi_eligible}

    d = players.drop_duplicates("player_id").copy()
    d = d[d["position"].isin(SQUAD_COUNTS)].reset_index(drop=True)
    if d.empty or projection_col not in projections.columns:
        return TransferPlan("Infeasible", float("nan"), [])

    club_col = "team" if "team" in d.columns else "team_name"
    if club_col not in d.columns:
        raise ValueError("players require team or team_name for club constraints")

    px = projections[projections["gw"].astype(int).isin(gws)][
        ["player_id", "gw", projection_col]
    ].copy()
    px[projection_col] = pd.to_numeric(px[projection_col], errors="coerce").fillna(0.0)
    matrix = px.pivot_table(
        index="player_id",
        columns="gw",
        values=projection_col,
        aggfunc="sum",
        fill_value=0.0,
    )
    for gw in gws:
        if gw not in matrix.columns:
            matrix[gw] = 0.0
    d = d[d["player_id"].isin(matrix.index)].reset_index(drop=True)
    if d.empty:
        return TransferPlan("Infeasible", float("nan"), [])

    n, T = len(d), len(gws)
    pids = d["player_id"].astype(int).tolist()
    by_id = {pid: i for i, pid in enumerate(pids)}
    prices = pd.to_numeric(d["price"], errors="coerce").fillna(99.0).to_numpy(float)
    xpv = np.zeros((n, T), dtype=float)
    for i, pid in enumerate(pids):
        if pid in matrix.index:
            xpv[i, :] = [float(matrix.loc[pid, gw]) for gw in gws]

    # Per player/week variables: squad, XI, captain, transfer-in, transfer-out.
    block = n * T
    S0, X0, C0, IN0, OUT0 = 0, block, 2 * block, 3 * block, 4 * block
    BANK0 = 5 * block

    # FT/action one-hot exists only for GW2 onward. There is no transfer decision
    # before the GW1 deadline because the initial 15 is selected freely.
    future_weeks = max(T - 1, 0)
    Y0 = BANK0 + T
    F = MAX_ROLLED_FREE_TRANSFERS
    K = 16
    y_count = future_weeks * F * K
    m = Y0 + y_count

    def q(base_idx: int, i: int, t: int) -> int:
        return base_idx + t * n + i

    def y(t: int, ft: int, k: int) -> int:
        # t is the absolute horizon index and must be >= 1.
        return Y0 + (((t - 1) * F + (ft - 1)) * K + k)

    objective = np.zeros(m, dtype=float)
    for t in range(T):
        disc = float(decay) ** t
        for i in range(n):
            value = max(float(xpv[i, t]), 0.0) * disc
            objective[q(S0, i, t)] += 0.08 * value
            objective[q(X0, i, t)] += 0.92 * value
            objective[q(C0, i, t)] += value
        if t >= 1:
            for ft in range(1, F + 1):
                for k in range(K):
                    objective[y(t, ft, k)] -= TRANSFER_HIT_COST * max(0, k - ft)

    rows: list[dict[int, float]] = []
    lower: list[float] = []
    upper: list[float] = []

    def add(coeffs: dict[int, float], lo: float, hi: float) -> None:
        rows.append(coeffs)
        lower.append(lo)
        upper.append(hi)

    for t in range(T):
        add({q(S0, i, t): 1.0 for i in range(n)}, 15, 15)
        add({q(X0, i, t): 1.0 for i in range(n)}, 11, 11)
        add({q(C0, i, t): 1.0 for i in range(n)}, 1, 1)

        if captain_eligible is not None:
            eligible_idx = [i for i, pid in enumerate(pids) if pid in captain_eligible]
            add({q(X0, i, t): 1.0 for i in eligible_idx}, 2, np.inf)

        for pos, count in SQUAD_COUNTS.items():
            idx = [i for i in range(n) if d.loc[i, "position"] == pos]
            add({q(S0, i, t): 1.0 for i in idx}, count, count)
            add({q(X0, i, t): 1.0 for i in idx}, XI_MIN[pos], XI_MAX[pos])

        for team in d[club_col].dropna().unique():
            idx = [i for i in range(n) if d.loc[i, club_col] == team]
            add({q(S0, i, t): 1.0 for i in idx}, -np.inf, max_per_team)

        for i in range(n):
            add({q(X0, i, t): 1.0, q(S0, i, t): -1.0}, -np.inf, 0)
            add({q(C0, i, t): 1.0, q(X0, i, t): -1.0}, -np.inf, 0)
            add({q(IN0, i, t): 1.0, q(OUT0, i, t): 1.0}, -np.inf, 1)

            if t >= 1:
                add(
                    {
                        q(S0, i, t): 1.0,
                        q(S0, i, t - 1): -1.0,
                        q(IN0, i, t): -1.0,
                        q(OUT0, i, t): 1.0,
                    },
                    0,
                    0,
                )

        if t == 0:
            # Initial squad is purchased freely from the £100m budget. The
            # remainder is the actual bank carried into GW2.
            cash = {BANK0: 1.0}
            cash.update({q(S0, i, 0): float(prices[i]) for i in range(n)})
            add(cash, float(budget), float(budget))
        else:
            balance = {q(IN0, i, t): 1.0 for i in range(n)}
            balance.update({q(OUT0, i, t): -1.0 for i in range(n)})
            add(balance, 0, 0)

            add(
                {y(t, ft, k): 1.0 for ft in range(1, F + 1) for k in range(K)},
                1,
                1,
            )
            count = {q(IN0, i, t): 1.0 for i in range(n)}
            count.update(
                {y(t, ft, k): -float(k) for ft in range(1, F + 1) for k in range(K)}
            )
            add(count, 0, 0)

            if t == 1:
                # FPL managers start GW2 with one free transfer. The free initial
                # GW1 squad must not be treated as an unused transfer that rolls.
                add({y(t, 1, k): 1.0 for k in range(K)}, 1, 1)
            else:
                for ft_now in range(1, F + 1):
                    lhs = {y(t, ft_now, k): 1.0 for k in range(K)}
                    for ft_prev in range(1, F + 1):
                        for k_prev in range(K):
                            next_state = _next_ft(ft_prev, k_prev)
                            if next_state == ft_now:
                                idx = y(t - 1, ft_prev, k_prev)
                                lhs[idx] = lhs.get(idx, 0.0) - 1.0
                    add(lhs, 0, 0)

            cash = {BANK0 + t: 1.0, BANK0 + t - 1: -1.0}
            for i in range(n):
                cash[q(IN0, i, t)] = cash.get(q(IN0, i, t), 0.0) + float(prices[i])
                cash[q(OUT0, i, t)] = cash.get(q(OUT0, i, t), 0.0) - float(prices[i])
            add(cash, 0, 0)

    # No-good cuts enumerate genuinely distinct GW1 starting squads rather than
    # static-horizon candidates.
    for excluded in excluded_initial_squads:
        idx = [i for i, pid in enumerate(pids) if pid in excluded]
        if len(idx) == 15:
            add({q(S0, i, 0): 1.0 for i in idx}, -np.inf, 14)

    lb = np.zeros(m, dtype=float)
    ub = np.ones(m, dtype=float)
    integrality = np.ones(m, dtype=int)
    for t in range(T):
        lb[BANK0 + t] = 0.0
        ub[BANK0 + t] = float(budget)
        integrality[BANK0 + t] = 0

    # There is no transfer action in the initial-squad selection week.
    for i in range(n):
        ub[q(IN0, i, 0)] = 0.0
        ub[q(OUT0, i, 0)] = 0.0

    for pid in locked:
        if pid in by_id:
            for t in range(T):
                lb[q(S0, by_id[pid], t)] = 1.0
    for pid in banned:
        if pid in by_id:
            for t in range(T):
                ub[q(S0, by_id[pid], t)] = 0.0

    if captain_eligible is not None:
        for i, pid in enumerate(pids):
            if pid not in captain_eligible:
                for t in range(T):
                    ub[q(C0, i, t)] = 0.0
    if xi_eligible is not None:
        for i, pid in enumerate(pids):
            if pid not in xi_eligible:
                for t in range(T):
                    ub[q(X0, i, t)] = 0.0

    A = lil_matrix((len(rows), m), dtype=float)
    for r, coeffs in enumerate(rows):
        for col, value in coeffs.items():
            A[r, col] = value

    result = milp(
        c=-objective,
        integrality=integrality,
        bounds=Bounds(lb, ub),
        constraints=LinearConstraint(
            A.tocsr(), np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)
        ),
        options={
            "time_limit": int(max(solver_time_limit, 1)),
            "mip_rel_gap": float(max(solver_relative_gap, 0.0)),
        },
    )
    if not result.success or result.x is None:
        return TransferPlan("Infeasible", float("nan"), [])

    sol = result.x
    weeks: list[dict] = []

    def records(indices: list[int], t: int) -> list[dict]:
        cols = [
            col
            for col in ["player_id", "web_name", "team_name", "position", "price"]
            if col in d.columns
        ]
        out = d.loc[indices, cols].copy()
        out["xp"] = [xpv[i, t] for i in indices]
        return out.to_dict("records")

    for t, gw in enumerate(gws):
        squad_i = [i for i in range(n) if sol[q(S0, i, t)] > 0.5]
        xi_i = [i for i in range(n) if sol[q(X0, i, t)] > 0.5]
        cap_i = [i for i in range(n) if sol[q(C0, i, t)] > 0.5]
        vice_pool = [
            i
            for i in xi_i
            if i not in cap_i
            and (captain_eligible is None or pids[i] in captain_eligible)
        ]
        vice_i = [max(vice_pool, key=lambda i: xpv[i, t])] if vice_pool else []
        in_i = [i for i in range(n) if sol[q(IN0, i, t)] > 0.5]
        out_i = [i for i in range(n) if sol[q(OUT0, i, t)] > 0.5]

        if t == 0:
            ft, k, hit = 0, 0, 0
        else:
            ft, k = next(
                (
                    (ft_state, transfers)
                    for ft_state in range(1, F + 1)
                    for transfers in range(K)
                    if sol[y(t, ft_state, transfers)] > 0.5
                ),
                (1, len(in_i)),
            )
            hit = int(max(0, k - ft) * TRANSFER_HIT_COST)

        transfer_out_records = records(out_i, t)
        for record, i in zip(transfer_out_records, out_i):
            record["selling_price"] = round(float(prices[i]), 1)

        weeks.append(
            {
                "gw": int(gw),
                "free_transfers_before": int(ft),
                "transfers": int(k),
                "hit_cost": int(hit),
                "bank_after": round(float(sol[BANK0 + t]), 2),
                "chip": None,
                "transfers_in": records(in_i, t),
                "transfers_out": transfer_out_records,
                "captain": records(cap_i, t),
                "vice_captain": records(vice_i, t),
                "xi": records(xi_i, t),
                "squad": records(squad_i, t),
            }
        )

    return TransferPlan("Optimal", float(-result.fun), weeks)
