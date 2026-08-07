from __future__ import annotations

import numpy as np
import pandas as pd

from apex_fpl.models.scenarios import ProjectionScenarios
from apex_fpl.optimisation.frequencies import estimate_decision_frequencies


def _players() -> pd.DataFrame:
    rows = []
    pid = 1
    for position, count in (("GK", 3), ("DEF", 7), ("MID", 7), ("FWD", 5)):
        for _ in range(count):
            rows.append(
                {
                    "player_id": pid,
                    "web_name": f"P{pid}",
                    "team": (pid % 10) + 1,
                    "team_name": f"T{(pid % 10) + 1}",
                    "position": position,
                    "price": 4.0,
                    "appearance_probability": 0.95,
                }
            )
            pid += 1
    return pd.DataFrame(rows)


def test_decision_frequencies_re_solve_scenario_surfaces():
    players = _players()
    pids = players["player_id"].to_numpy(int)
    rng = np.random.default_rng(7)
    values = rng.uniform(1.5, 6.0, size=(4, len(pids), 2))
    scenarios = ProjectionScenarios(
        player_ids=pids,
        gameweeks=np.asarray([1, 2]),
        values=values,
        seed=7,
    )
    out = estimate_decision_frequencies(
        players,
        scenarios,
        budget=100.0,
        max_solves=4,
    )
    assert out.completed_solves == 4
    assert out.rows["squad_frequency"].sum() == 15
    assert out.rows["xi_frequency"].sum() == 11
    assert out.rows["captain_frequency"].sum() == 1
    assert out.rows["vice_captain_frequency"].sum() == 1
