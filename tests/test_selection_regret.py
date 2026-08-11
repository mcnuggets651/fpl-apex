import pandas as pd

from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.stability import selection_regret_analysis


def _pool():
    rows = []
    pid = 1
    for pos, count in [("GK", 3), ("DEF", 7), ("MID", 7), ("FWD", 5)]:
        for j in range(count):
            rows.append(
                {
                    "player_id": pid,
                    "web_name": f"P{pid}",
                    "team": (pid % 10) + 1,
                    "team_name": f"T{(pid % 10) + 1}",
                    "position": pos,
                    "price": 4.0 + (j % 3) * 0.5,
                    "gw1_xp": 2.0 + pid / 100,
                    "horizon_xp": 8.0 + pid / 20,
                    "appearance_probability": 0.95,
                }
            )
            pid += 1
    return pd.DataFrame(rows)


def _projections(players):
    return pd.DataFrame(
        [
            {
                "player_id": int(row.player_id),
                "gw": gw,
                "risk_adjusted_xp": 2.0 + row.player_id / 100 + gw / 20,
            }
            for row in players.itertuples(index=False)
            for gw in [1, 2, 3]
        ]
    )


def test_regret_analysis_re_solves_selected_and_alternative_players():
    players = _pool()
    projections = _projections(players)
    baseline = optimise_initial_horizon(
        players,
        projections,
        [1, 2, 3],
        budget=100.0,
        decay=1.0,
    )
    assert baseline.status == "Optimal"
    assert baseline.solver["incumbent"] == baseline.objective
    assert baseline.solver["bound"] is not None
    assert baseline.solver["relative_gap"] is not None
    assert baseline.solver["termination_reason"]

    stress = selection_regret_analysis(
        players,
        projections,
        [1, 2, 3],
        baseline,
        budget=100.0,
        decay=1.0,
        alternative_limit=3,
    )
    assert not stress.empty
    assert (stress["objective_regret"] >= -1e-7).all()
    assert set(stress["stress_type"]) == {"ban_selected", "force_alternative"}
    selected = stress[stress.selected]
    alternatives = stress[~stress.selected]
    assert len(selected) == 15
    assert 1 <= len(alternatives) <= 3
    assert selected["added_player_ids"].map(len).ge(1).all()
    assert selected["removed_player_ids"].map(len).eq(1).all()
    assert alternatives["added_player_ids"].map(len).eq(1).all()
    assert alternatives["removed_player_ids"].map(len).ge(1).all()
