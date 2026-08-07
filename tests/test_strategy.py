import pandas as pd

from apex_fpl.optimisation.transfers import TransferPlan
from apex_fpl.services.strategy import analyse_receding_horizon
from apex_fpl.services.team_state import TeamState


def _pool():
    rows = []
    pid = 1
    for team in range(1, 9):
        for pos, count in [("GK", 1), ("DEF", 2), ("MID", 2), ("FWD", 1)]:
            for _ in range(count):
                rows.append(
                    {
                        "player_id": pid,
                        "web_name": f"P{pid}",
                        "team_name": f"T{team}",
                        "position": pos,
                        "price": 4.5,
                        "horizon_xp": 20 + pid / 10,
                        "gw1_xp": 3 + pid / 100,
                    }
                )
                pid += 1
    return pd.DataFrame(rows)


def _current(players):
    ids = set()
    for pos, need in {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}.items():
        ids.update(players[players.position == pos].head(need).player_id.astype(int))
    return ids


def test_receding_horizon_exposes_only_first_action_as_actionable():
    players = _pool()
    current = _current(players)
    projections = pd.DataFrame(
        [
            {"player_id": int(pid), "gw": 1, "risk_adjusted_xp": 3.0 + int(pid) / 100}
            for pid in players.player_id
        ]
    )
    plan = TransferPlan(
        status="Optimal",
        objective=80.0,
        weeks=[
            {
                "gw": 1,
                "transfers": 1,
                "hit_cost": 0,
                "transfers_in": [{"player_id": 40}],
                "transfers_out": [{"player_id": 1}],
            },
            {"gw": 2, "transfers": 1, "hit_cost": 0},
        ],
    )
    state = TeamState(squad=current, bank=5.0, free_transfers=1)
    out = analyse_receding_horizon(players, projections, [1], state, plan)
    assert out.status == "optimal"
    assert out.recommended_action == "one_free_transfer"
    assert out.action_now["gw"] == 1
    assert out.contingent_future[0]["gw"] == 2
    assert out.roll_objective is not None
    assert out.roll_regret is not None


def test_receding_horizon_handles_missing_plan():
    players = _pool()
    current = _current(players)
    state = TeamState(squad=current)
    out = analyse_receding_horizon(players, pd.DataFrame(), [1], state, None)
    assert out.status == "unavailable"
    assert out.recommended_action == "none"
