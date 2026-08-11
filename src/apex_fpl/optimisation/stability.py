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
    projection_col: str = "xp",
    captain_eligible: set[int] | None = None,
) -> pd.DataFrame:
    """Measure exact objective regret from forcing/excluding individual players.

    Every stress solve uses the exact same projection surface as the baseline. The
    unselected alternative shortlist is also ranked from that surface rather than
    from a precomputed risk-adjusted summary, preventing a strong maximum-EV
    alternative from being omitted before the exact force test is run.
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
        "added_player_ids",
        "added_player_names",
        "removed_player_ids",
        "removed_player_names",
    ]
    if baseline.status != "Optimal" or baseline.squad.empty:
        return pd.DataFrame(columns=columns)

    locked = set(locked or set())
    banned = set(banned or set())
    baseline_obj = float(baseline.objective)
    selected_ids = set(
        pd.to_numeric(baseline.squad["player_id"], errors="coerce")
        .dropna()
        .astype(int)
    )
    name_cols = [c for c in ["player_id", "web_name"] if c in players.columns]
    names = {
        int(row.player_id): str(getattr(row, "web_name", row.player_id))
        for row in players[name_cols].itertuples(index=False)
    }

    rows: list[dict] = []

    def changes(stressed: SquadSolution) -> dict[str, list]:
        stressed_ids = (
            set(
                pd.to_numeric(stressed.squad["player_id"], errors="coerce")
                .dropna()
                .astype(int)
            )
            if not stressed.squad.empty and "player_id" in stressed.squad
            else set()
        )
        added = sorted(stressed_ids - selected_ids)
        removed = sorted(selected_ids - stressed_ids)
        return {
            "added_player_ids": added,
            "added_player_names": [names.get(value, str(value)) for value in added],
            "removed_player_ids": removed,
            "removed_player_names": [names.get(value, str(value)) for value in removed],
        }

    common = dict(
        players=players,
        projections=projections,
        gameweeks=gameweeks,
        budget=budget,
        max_per_team=max_per_team,
        decay=decay,
        bench_weight=bench_weight,
        captain_eligible=captain_eligible,
        projection_col=projection_col,
    )

    for pid in sorted(selected_ids):
        if pid in locked:
            continue
        stressed = optimise_initial_horizon(
            **common,
            locked=locked,
            banned=banned | {pid},
        )
        constrained = (
            float(stressed.objective) if stressed.status == "Optimal" else math.nan
        )
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
                **changes(stressed),
            }
        )

    candidates = players[
        ~players["player_id"].astype(int).isin(selected_ids | banned)
    ].copy()
    value_col = (
        projection_col
        if projection_col in projections.columns
        else "risk_adjusted_xp"
    )
    if value_col in projections.columns and gameweeks:
        px = projections[projections["gw"].isin(gameweeks)][
            ["player_id", "gw", value_col]
        ].copy()
        gw_weight = {
            int(gw): float(decay) ** idx for idx, gw in enumerate(gameweeks)
        }
        px["_weight"] = px["gw"].map(gw_weight).fillna(0.0)
        px["_value"] = (
            pd.to_numeric(px[value_col], errors="coerce").fillna(0.0)
            * px["_weight"]
        )
        scores = px.groupby("player_id")["_value"].sum()
        candidates["_stress_score"] = (
            candidates["player_id"].map(scores).fillna(0.0)
        )
        candidates = candidates.nlargest(
            max(int(alternative_limit), 0), "_stress_score"
        )
    else:
        candidates = candidates.head(max(int(alternative_limit), 0))

    candidate_ids = pd.to_numeric(
        candidates.get("player_id", pd.Series(dtype=float)), errors="coerce"
    ).dropna().astype(int)
    for pid in candidate_ids:
        if pid in banned:
            continue
        stressed = optimise_initial_horizon(
            **common,
            locked=locked | {int(pid)},
            banned=banned,
        )
        constrained = (
            float(stressed.objective) if stressed.status == "Optimal" else math.nan
        )
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
                **changes(stressed),
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
