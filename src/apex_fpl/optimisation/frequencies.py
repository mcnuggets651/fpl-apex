from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from apex_fpl.models.scenarios import ProjectionScenarios
from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.mechanics import optimise_gameweek_mechanics


@dataclass(frozen=True)
class DecisionFrequencies:
    requested_solves: int
    completed_solves: int
    rows: pd.DataFrame


@dataclass(frozen=True)
class CaptainFrequencies:
    requested_solves: int
    completed_solves: int
    rows: pd.DataFrame


def _appearance_map(players: pd.DataFrame) -> dict[int, float]:
    names = players.drop_duplicates("player_id")
    return {
        int(pid): float(prob)
        for pid, prob in zip(
            names["player_id"].astype(int),
            pd.to_numeric(
                names.get("appearance_probability", pd.Series(1.0, index=names.index)),
                errors="coerce",
            ).fillna(1.0),
        )
    }


def estimate_decision_frequencies(
    players: pd.DataFrame,
    scenarios: ProjectionScenarios,
    *,
    budget: float = 100.0,
    max_per_team: int = 3,
    decay: float = 0.90,
    max_solves: int = 24,
    captain_eligible: set[int] | None = None,
) -> DecisionFrequencies:
    """Re-solve plausible forecast surfaces and count whole-decision persistence.

    This measures how often players remain in the globally optimal squad/XI when
    the complete projection surface changes. It is deliberately separate from
    captain stability conditional on the published XI.
    """
    requested = min(max(int(max_solves), 1), scenarios.n_scenarios)
    indices = np.linspace(0, scenarios.n_scenarios - 1, requested, dtype=int)
    pids = [int(pid) for pid in scenarios.player_ids]
    gws = [int(gw) for gw in scenarios.gameweeks]
    names = players.drop_duplicates("player_id")
    appearance = _appearance_map(players)
    counters = {
        pid: {"squad": 0, "xi": 0, "captain": 0, "vice": 0}
        for pid in pids
    }
    completed = 0

    for scenario_index in indices:
        values = scenarios.values[int(scenario_index)]
        projection = pd.DataFrame(
            [
                {"player_id": pid, "gw": gw, "xp": float(values[p_i, g_i])}
                for p_i, pid in enumerate(pids)
                for g_i, gw in enumerate(gws)
            ]
        )
        solution = optimise_initial_horizon(
            players,
            projection,
            gws,
            budget=budget,
            max_per_team=max_per_team,
            decay=decay,
            captain_eligible=captain_eligible,
            projection_col="xp",
        )
        if solution.status != "Optimal":
            continue
        completed += 1
        squad_ids = set(solution.squad["player_id"].astype(int))
        xi_ids = set(solution.xi["player_id"].astype(int))
        gw1_xp = {
            int(pid): float(value)
            for pid, value in projection[projection["gw"] == gws[0]]
            .groupby("player_id")["xp"]
            .sum()
            .items()
        }
        mechanics = optimise_gameweek_mechanics(
            solution.squad,
            solution.xi,
            gw1_xp,
            appearance,
            captain_eligible=captain_eligible,
        )
        for pid in squad_ids:
            counters[pid]["squad"] += 1
        for pid in xi_ids:
            counters[pid]["xi"] += 1
        counters[mechanics.captain_id]["captain"] += 1
        counters[mechanics.vice_captain_id]["vice"] += 1

    if completed == 0:
        return DecisionFrequencies(requested, 0, pd.DataFrame())
    rows = pd.DataFrame(
        [
            {
                "player_id": pid,
                "squad_frequency": counts["squad"] / completed,
                "xi_frequency": counts["xi"] / completed,
                "captain_frequency": counts["captain"] / completed,
                "vice_captain_frequency": counts["vice"] / completed,
            }
            for pid, counts in counters.items()
        ]
    )
    keep = [
        col
        for col in ("player_id", "web_name", "team_name", "position", "price")
        if col in names.columns
    ]
    rows = rows.merge(names[keep], on="player_id", how="left", validate="one_to_one")
    return DecisionFrequencies(
        requested,
        completed,
        rows.sort_values(
            ["squad_frequency", "xi_frequency", "captain_frequency"],
            ascending=False,
        ).reset_index(drop=True),
    )


def estimate_fixed_xi_captain_frequencies(
    players: pd.DataFrame,
    scenarios: ProjectionScenarios,
    squad: pd.DataFrame,
    xi: pd.DataFrame,
    *,
    max_solves: int = 24,
    captain_eligible: set[int] | None = None,
) -> CaptainFrequencies:
    """Measure captain/vice persistence while holding the published squad/XI fixed.

    This answers the actual deadline question: given the XI we intend to own and
    start, how often does the same captain remain optimal as plausible GW1 outcomes
    move? It intentionally does not confound captain robustness with whether a
    different uncertainty surface would have selected an entirely different squad.
    """
    if squad.empty or xi.empty:
        return CaptainFrequencies(0, 0, pd.DataFrame())

    requested = min(max(int(max_solves), 1), scenarios.n_scenarios)
    indices = np.linspace(0, scenarios.n_scenarios - 1, requested, dtype=int)
    pids = [int(pid) for pid in scenarios.player_ids]
    pid_index = {pid: idx for idx, pid in enumerate(pids)}
    gw1_index = 0
    names = players.drop_duplicates("player_id")
    appearance = _appearance_map(players)
    xi_ids = [int(pid) for pid in xi["player_id"].astype(int)]
    counters = {pid: {"captain": 0, "vice": 0} for pid in xi_ids}
    completed = 0

    for scenario_index in indices:
        values = scenarios.values[int(scenario_index)]
        gw1_xp = {
            pid: float(values[pid_index[pid], gw1_index])
            for pid in xi_ids
            if pid in pid_index
        }
        if len(gw1_xp) != len(xi_ids):
            continue
        mechanics = optimise_gameweek_mechanics(
            squad,
            xi,
            gw1_xp,
            appearance,
            captain_eligible=captain_eligible,
        )
        completed += 1
        counters[mechanics.captain_id]["captain"] += 1
        counters[mechanics.vice_captain_id]["vice"] += 1

    if completed == 0:
        return CaptainFrequencies(requested, 0, pd.DataFrame())

    rows = pd.DataFrame(
        [
            {
                "player_id": pid,
                "captain_frequency": counts["captain"] / completed,
                "vice_captain_frequency": counts["vice"] / completed,
            }
            for pid, counts in counters.items()
        ]
    )
    keep = [
        col
        for col in ("player_id", "web_name", "team_name", "position", "price")
        if col in names.columns
    ]
    rows = rows.merge(names[keep], on="player_id", how="left", validate="one_to_one")
    return CaptainFrequencies(
        requested,
        completed,
        rows.sort_values(
            ["captain_frequency", "vice_captain_frequency"],
            ascending=False,
        ).reset_index(drop=True),
    )
