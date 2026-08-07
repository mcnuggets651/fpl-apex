from __future__ import annotations

import math

import pandas as pd

from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.squad import SquadSolution


def selection_regret_analysis(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    baseline: SquadSolution,
    *,
    budget: float = 100.0,
    max_per_team: int = 3,
    decay: float = 0.90,
    bench_weight: float = 0.08,
    locked: set[int] | None = None,
    banned: set[int] | None = None,
    alternative_limit: int = 12,
) -> pd.DataFrame:
    """Measure exact objective regret from forcing/excluding individual players.

    This is a deterministic sensitivity analysis on the *same* projection surface.
    For every selected player we re-solve with that player banned. For the strongest
    unselected alternatives we re-solve with the player forced into the squad.

    A large positive regret means the baseline decision is structurally robust;
    a regret close to zero means the pick sits inside a near-optimal cluster and
    should be treated as fragile to small projection/news changes.
    """
    columns = [
        "player_id",
        "web_name",
        "selected",
        "stress_type",
        "baseline_objective",
        "constrained_objective",
        "objective_regret",
        "constrained_status",
    ]
    if baseline.status != "Optimal" or baseline.squad.empty:
        return pd.DataFrame(columns=columns)

    locked = set(locked or set())
    banned = set(banned or set())
    baseline_obj = float(baseline.objective)
    selected_ids = set(pd.to_numeric(baseline.squad["player_id"], errors="coerce").dropna().astype(int))
    names = {
        int(row.player_id): str(getattr(row, "web_name", row.player_id))
        for row in players[[c for c in ["player_id", "web_name"] if c in players.columns]].itertuples(index=False)
    }

    rows: list[dict] = []

    for pid in sorted(selected_ids):
        if pid in locked:
            continue
        stressed = optimise_initial_horizon(
            players,
            projections,
            gameweeks,
            budget=budget,
            max_per_team=max_per_team,
            decay=decay,
            bench_weight=bench_weight,
            locked=locked,
            banned=banned | {pid},
        )
        constrained = float(stressed.objective) if stressed.status == "Optimal" else math.nan
        regret = baseline_obj - constrained if math.isfinite(constrained) else math.inf
        rows.append(
            {
                "player_id": pid,
                "web_name": names.get(pid, str(pid)),
                "selected": True,
                "stress_type": "ban_selected",
                "baseline_objective": baseline_obj,
                "constrained_objective": constrained,
                "objective_regret": regret,
                "constrained_status": stressed.status,
            }
        )

    candidates = players[~players["player_id"].astype(int).isin(selected_ids | banned)].copy()
    sort_col = "horizon_xp" if "horizon_xp" in candidates.columns else "gw1_xp"
    if sort_col in candidates.columns:
        candidates[sort_col] = pd.to_numeric(candidates[sort_col], errors="coerce").fillna(0.0)
        candidates = candidates.nlargest(max(int(alternative_limit), 0), sort_col)
    else:
        candidates = candidates.head(max(int(alternative_limit), 0))

    for pid in pd.to_numeric(candidates.get("player_id", pd.Series(dtype=float)), errors="coerce").dropna().astype(int):
        if pid in banned:
            continue
        stressed = optimise_initial_horizon(
            players,
            projections,
            gameweeks,
            budget=budget,
            max_per_team=max_per_team,
            decay=decay,
            bench_weight=bench_weight,
            locked=locked | {int(pid)},
            banned=banned,
        )
        constrained = float(stressed.objective) if stressed.status == "Optimal" else math.nan
        regret = baseline_obj - constrained if math.isfinite(constrained) else math.inf
        rows.append(
            {
                "player_id": int(pid),
                "web_name": names.get(int(pid), str(pid)),
                "selected": False,
                "stress_type": "force_alternative",
                "baseline_objective": baseline_obj,
                "constrained_objective": constrained,
                "objective_regret": regret,
                "constrained_status": stressed.status,
            }
        )

    out = pd.DataFrame(rows, columns=columns)
    if out.empty:
        return out
    return out.sort_values(
        ["selected", "objective_regret"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)
