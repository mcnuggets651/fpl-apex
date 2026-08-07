import pandas as pd

from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon


def _pool():
    rows = []
    pid = 1
    for pos, count in [("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 2)]:
        for _ in range(count):
            rows.append(
                {
                    "player_id": pid,
                    "web_name": f"P{pid}",
                    "team_name": f"T{pid}",
                    "position": pos,
                    "price": 4.0,
                    "horizon_xp": 10.0,
                }
            )
            pid += 1
    rows += [
        {
            "player_id": 15,
            "web_name": "HighEV",
            "team_name": "T15",
            "position": "FWD",
            "price": 4.0,
            "horizon_xp": 10.0,
        },
        {
            "player_id": 16,
            "web_name": "Safer",
            "team_name": "T16",
            "position": "FWD",
            "price": 4.0,
            "horizon_xp": 10.0,
        },
    ]
    return pd.DataFrame(rows)


def test_default_horizon_solver_maximises_ensemble_mean_xp():
    players = _pool()
    projections = pd.DataFrame(
        [
            {
                "player_id": int(pid),
                "gw": 1,
                "xp": 2.0,
                "risk_adjusted_xp": 2.0,
            }
            for pid in players.player_id
        ]
    )
    # Two incumbent forwards are clearly fixed. The final FWD slot is the only
    # decision: raw EV prefers 15 while a risk-adjusted surface prefers 16.
    projections.loc[projections.player_id.isin([13, 14]), ["xp", "risk_adjusted_xp"]] = [20.0, 20.0]
    projections.loc[projections.player_id == 15, ["xp", "risk_adjusted_xp"]] = [8.0, 3.0]
    projections.loc[projections.player_id == 16, ["xp", "risk_adjusted_xp"]] = [6.0, 5.0]

    ev = optimise_initial_horizon(players, projections, [1], decay=1.0)
    risk = optimise_initial_horizon(
        players,
        projections,
        [1],
        decay=1.0,
        projection_col="risk_adjusted_xp",
    )
    assert ev.status == "Optimal"
    assert risk.status == "Optimal"
    assert 15 in set(ev.squad.player_id)
    assert 16 not in set(ev.squad.player_id)
    assert 16 in set(risk.squad.player_id)
    assert 15 not in set(risk.squad.player_id)
