from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from apex_fpl.constants import SQUAD_COUNTS, XI_MAX, XI_MIN
from apex_fpl.rules import MAX_ROLLED_FREE_TRANSFERS, TRANSFER_HIT_COST


@dataclass
class TransferPlan:
    status: str
    objective: float
    weeks: list[dict]
    solver_status_code: int | None = None
    solver_message: str | None = None
    objective_upper_bound: float | None = None
    mip_gap: float | None = None


def _finite_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _next_ft(ft: int, transfers: int) -> int:
    return min(MAX_ROLLED_FREE_TRANSFERS, max(1, ft - transfers + 1))


def optimise_transfer_plan(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    current_squad: set[int],
    bank: float = 0.0,
    free_transfers: int = 1,
    max_per_team: int = 3,
    decay: float = 0.92,
    locked: set[int] | None = None,
    banned: set[int] | None = None,
    wildcard_gw: int | None = None,
    bench_boost_gw: int | None = None,
    triple_captain_gw: int | None = None,
    candidate_limit: int = 110,
    selling_prices: dict[int, float] | None = None,
    captain_eligible: set[int] | None = None,
    solver_time_limit: float = 120.0,
    solver_relative_gap: float = 0.002,
) -> TransferPlan:
    """Multi-period FPL transfer MILP with exact rolled-FT state transitions.

    The model plans squad, XI, captain, transfers, bank and transfer hits over a
    horizon. Purchase prices are held at the current official snapshot. For the
    manager's existing squad, ``selling_prices`` can provide the actual FPL cash
    realised on a sale rather than incorrectly assuming every player sells at the
    current market price.

    Supported fixed chips: Wildcard, Bench Boost and Triple Captain. Free Hit is
    intentionally evaluated as a separate one-week scenario because its squad
    reversion semantics are different from permanent transfer planning.

    Solver-limit termination is deliberately distinct from mathematical
    infeasibility. A time/iteration limit may still have a feasible incumbent and a
    branch-and-bound objective bound; callers can use that bound for safe pruning or
    retry the same model without falsely escalating to a larger universe.
    """
    locked, banned = locked or set(), banned or set()
    captain_eligible = (
        None if captain_eligible is None else {int(pid) for pid in captain_eligible}
    )
    xi_eligible = (
        set(
            players.loc[
                players["xi_evidence_eligible"].fillna(False), "player_id"
            ].astype(int)
        )
        if "xi_evidence_eligible" in players
        else None
    )
    selling_prices = selling_prices or {}
    if not gameweeks:
        return TransferPlan("Infeasible", float("nan"), [])

    base = players.drop_duplicates("player_id").copy()
    base = base[base["position"].isin(SQUAD_COUNTS)].copy()
    px = projections[projections["gw"].isin(gameweeks)][
        ["player_id", "gw", "risk_adjusted_xp"]
    ].copy()
    matrix = px.pivot_table(
        index="player_id",
        columns="gw",
        values="risk_adjusted_xp",
        aggfunc="sum",
        fill_value=0.0,
    )
    for gw in gameweeks:
        if gw not in matrix.columns:
            matrix[gw] = 0.0
    base = base[base["player_id"].isin(matrix.index)].copy()
    base["plan_xp"] = base["player_id"].map(matrix[gameweeks].sum(axis=1)).fillna(0)

    # Keep all existing/locked players plus the best candidates. This preserves
    # exact legality while preventing a needlessly huge branch-and-bound model.
    must_keep = set(map(int, current_squad)) | set(map(int, locked))
    if captain_eligible is not None:
        must_keep |= captain_eligible
    top = set(base.nlargest(candidate_limit, "plan_xp")["player_id"].astype(int))
    d = base[base["player_id"].astype(int).isin(top | must_keep)].reset_index(drop=True)
    if not current_squad.issubset(set(d["player_id"].astype(int))):
        return TransferPlan(
            "Infeasible: current squad IDs missing from player pool",
            float("nan"),
            [],
        )
    if len(current_squad) != 15:
        return TransferPlan(
            "Infeasible: current squad must contain 15 players",
            float("nan"),
            [],
        )

    n, T = len(d), len(gameweeks)
    pids = d["player_id"].astype(int).tolist()
    by_id = {pid: i for i, pid in enumerate(pids)}
    buy_prices = pd.to_numeric(d["price"], errors="coerce").fillna(0).to_numpy(float)
    sell_prices = np.array(
        [
            float(selling_prices.get(pid, buy_prices[i]))
            if pid in current_squad
            else float(buy_prices[i])
            for i, pid in enumerate(pids)
        ],
        dtype=float,
    )
    xpv = np.zeros((n, T), dtype=float)
    for i, pid in enumerate(pids):
        if pid in matrix.index:
            xpv[i, :] = [float(matrix.loc[pid, gw]) for gw in gameweeks]

    # Per player/week variables: squad, XI, captain, transfer-in, transfer-out.
    block = n * T
    S0, X0, C0, IN0, OUT0 = 0, block, 2 * block, 3 * block, 4 * block
    # Continuous bank per week.
    BANK0 = 5 * block
    # FT state/action one-hot y[t, ft=1..5, k=0..15]. Exact transition also
    # gives transfer-hit costs without max()/min() nonlinearities.
    Y0 = BANK0 + T
    F = MAX_ROLLED_FREE_TRANSFERS
    K = 16
    y_count = T * F * K
    m = Y0 + y_count

    def q(base_idx: int, i: int, t: int) -> int:
        return base_idx + t * n + i

    def y(t: int, ft: int, k: int) -> int:
        return Y0 + (t * F + (ft - 1)) * K + k

    objective = np.zeros(m, dtype=float)
    for t, gw in enumerate(gameweeks):
        disc = decay**t
        for i in range(n):
            # Small squad value rewards playable bench; XI and captain dominate.
            objective[q(S0, i, t)] += 0.08 * xpv[i, t] * disc
            if bench_boost_gw == gw:
                objective[q(S0, i, t)] += 0.92 * xpv[i, t] * disc
            else:
                objective[q(X0, i, t)] += 0.92 * xpv[i, t] * disc
            objective[q(C0, i, t)] += xpv[i, t] * disc
            if triple_captain_gw == gw:
                objective[q(C0, i, t)] += xpv[i, t] * disc
        if wildcard_gw != gw:
            for ft in range(1, F + 1):
                for k in range(K):
                    objective[y(t, ft, k)] -= TRANSFER_HIT_COST * max(0, k - ft)

    rows: list[dict[int, float]] = []
    lower: list[float] = []
    upper: list[float] = []

    def add(coeffs: dict[int, float], lo: float, hi: float):
        rows.append(coeffs)
        lower.append(lo)
        upper.append(hi)

    for t, gw in enumerate(gameweeks):
        add({q(S0, i, t): 1 for i in range(n)}, 15, 15)
        add({q(X0, i, t): 1 for i in range(n)}, 11, 11)
        add({q(C0, i, t): 1 for i in range(n)}, 1, 1)
        if captain_eligible is not None:
            eligible_idx = [i for i, pid in enumerate(pids) if pid in captain_eligible]
            add({q(X0, i, t): 1 for i in eligible_idx}, 2, np.inf)

        for pos, count in SQUAD_COUNTS.items():
            idx = [i for i in range(n) if d.loc[i, "position"] == pos]
            add({q(S0, i, t): 1 for i in idx}, count, count)
            add({q(X0, i, t): 1 for i in idx}, XI_MIN[pos], XI_MAX[pos])
        for team in d["team"].dropna().unique():
            idx = [i for i in range(n) if d.loc[i, "team"] == team]
            add({q(S0, i, t): 1 for i in idx}, -np.inf, max_per_team)
        for i in range(n):
            add({q(X0, i, t): 1, q(S0, i, t): -1}, -np.inf, 0)
            add({q(C0, i, t): 1, q(X0, i, t): -1}, -np.inf, 0)
            # No player can be transferred both ways in same GW.
            add({q(IN0, i, t): 1, q(OUT0, i, t): 1}, -np.inf, 1)

            prev = 1.0 if pids[i] in current_squad else 0.0
            if t == 0:
                # s_t = s_initial + in - out
                add(
                    {
                        q(S0, i, t): 1,
                        q(IN0, i, t): -1,
                        q(OUT0, i, t): 1,
                    },
                    prev,
                    prev,
                )
            else:
                add(
                    {
                        q(S0, i, t): 1,
                        q(S0, i, t - 1): -1,
                        q(IN0, i, t): -1,
                        q(OUT0, i, t): 1,
                    },
                    0,
                    0,
                )

        # Every permanent transfer is one in + one out.
        balance = {q(IN0, i, t): 1 for i in range(n)}
        balance.update({q(OUT0, i, t): -1 for i in range(n)})
        add(balance, 0, 0)

        # Exactly one (FT state, transfer-count) action pair per GW.
        add(
            {y(t, ft, k): 1 for ft in range(1, F + 1) for k in range(K)},
            1,
            1,
        )
        # Transfer count links to transfer-ins.
        coeff = {q(IN0, i, t): 1 for i in range(n)}
        coeff.update(
            {y(t, ft, k): -k for ft in range(1, F + 1) for k in range(K)}
        )
        add(coeff, 0, 0)
        if t == 0:
            add({y(t, free_transfers, k): 1 for k in range(K)}, 1, 1)
        else:
            # The FT state at t must equal the deterministic transition from t-1.
            for ft_now in range(1, F + 1):
                lhs = {y(t, ft_now, k): 1 for k in range(K)}
                for ft_prev in range(1, F + 1):
                    for k_prev in range(K):
                        previous_gw = gameweeks[t - 1]
                        next_state = (
                            ft_prev
                            if wildcard_gw == previous_gw
                            else _next_ft(ft_prev, k_prev)
                        )
                        if next_state == ft_now:
                            lhs[y(t - 1, ft_prev, k_prev)] = (
                                lhs.get(y(t - 1, ft_prev, k_prev), 0) - 1
                            )
                add(lhs, 0, 0)

        # Bank cash flow. Existing players use their manager-specific selling
        # prices; new purchases use the live official market price.
        cash = {BANK0 + t: 1}
        for i in range(n):
            cash[q(IN0, i, t)] = cash.get(q(IN0, i, t), 0) + buy_prices[i]
            cash[q(OUT0, i, t)] = cash.get(q(OUT0, i, t), 0) - sell_prices[i]
        if t == 0:
            add(cash, bank, bank)
        else:
            cash[BANK0 + t - 1] = -1
            add(cash, 0, 0)

    lb = np.zeros(m, dtype=float)
    ub = np.ones(m, dtype=float)
    integrality = np.ones(m, dtype=int)
    # Bank is continuous and nonnegative, with a generous upper bound.
    for t in range(T):
        lb[BANK0 + t] = 0
        ub[BANK0 + t] = 100
        integrality[BANK0 + t] = 0

    for pid in locked:
        if pid in by_id:
            for t in range(T):
                lb[q(S0, by_id[pid], t)] = 1
    for pid in banned:
        if pid in by_id:
            for t in range(T):
                ub[q(S0, by_id[pid], t)] = 0
    if captain_eligible is not None:
        for i, pid in enumerate(pids):
            if pid not in captain_eligible:
                for t in range(T):
                    ub[q(C0, i, t)] = 0
    if xi_eligible is not None:
        for i, pid in enumerate(pids):
            if pid not in xi_eligible:
                for t in range(T):
                    ub[q(X0, i, t)] = 0

    A = lil_matrix((len(rows), m), dtype=float)
    for r, coeffs in enumerate(rows):
        for col, val in coeffs.items():
            A[r, col] = val

    time_limit = max(float(solver_time_limit), 0.01)
    relative_gap = max(float(solver_relative_gap), 0.0)
    res = milp(
        c=-objective,
        integrality=integrality,
        bounds=Bounds(lb, ub),
        constraints=LinearConstraint(A.tocsr(), np.asarray(lower), np.asarray(upper)),
        options={"time_limit": time_limit, "mip_rel_gap": relative_gap},
    )

    status_code_raw = getattr(res, "status", None)
    status_code = int(status_code_raw) if status_code_raw is not None else None
    message_raw = getattr(res, "message", None)
    message = str(message_raw) if message_raw is not None else None
    incumbent_fun = _finite_float(getattr(res, "fun", None))
    incumbent_objective = (
        -float(incumbent_fun) if incumbent_fun is not None else float("nan")
    )
    dual_bound = _finite_float(getattr(res, "mip_dual_bound", None))
    objective_upper_bound = -float(dual_bound) if dual_bound is not None else None
    mip_gap = _finite_float(getattr(res, "mip_gap", None))

    if not bool(getattr(res, "success", False)) or getattr(res, "x", None) is None:
        status = {
            1: "SolverLimit",
            2: "Infeasible",
            3: "Unbounded",
            4: "SolverError",
        }.get(status_code, "SolverError")
        return TransferPlan(
            status,
            incumbent_objective,
            [],
            solver_status_code=status_code,
            solver_message=message,
            objective_upper_bound=objective_upper_bound,
            mip_gap=mip_gap,
        )

    sol = res.x
    weeks: list[dict] = []
    for t, gw in enumerate(gameweeks):
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
        chosen_state = next(
            (
                (ft, k)
                for ft in range(1, F + 1)
                for k in range(K)
                if sol[y(t, ft, k)] > 0.5
            ),
            (1, len(in_i)),
        )
        ft, k = chosen_state
        hit = (
            0
            if wildcard_gw == gw
            else int(max(0, k - ft) * TRANSFER_HIT_COST)
        )

        def records(indices: list[int]) -> list[dict]:
            cols = [
                col
                for col in [
                    "player_id",
                    "web_name",
                    "team_name",
                    "position",
                    "price",
                ]
                if col in d.columns
            ]
            out = d.loc[indices, cols].copy()
            out["xp"] = [xpv[i, t] for i in indices]
            return out.to_dict("records")

        transfer_out_records = records(out_i)
        for record, i in zip(transfer_out_records, out_i):
            record["selling_price"] = round(float(sell_prices[i]), 1)

        weeks.append(
            {
                "gw": int(gw),
                "free_transfers_before": int(ft),
                "transfers": int(k),
                "hit_cost": hit,
                "bank_after": round(float(sol[BANK0 + t]), 2),
                "chip": (
                    "wildcard"
                    if wildcard_gw == gw
                    else "bench_boost"
                    if bench_boost_gw == gw
                    else "triple_captain"
                    if triple_captain_gw == gw
                    else None
                ),
                "transfers_in": records(in_i),
                "transfers_out": transfer_out_records,
                "captain": records(cap_i),
                "vice_captain": records(vice_i),
                "xi": records(xi_i),
                "squad": records(squad_i),
            }
        )
    return TransferPlan(
        "Optimal",
        incumbent_objective,
        weeks,
        solver_status_code=status_code,
        solver_message=message,
        objective_upper_bound=objective_upper_bound,
        mip_gap=mip_gap,
    )