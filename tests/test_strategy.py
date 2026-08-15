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
                        "team": team,
                        "position": pos,
                        "price": 4.5,
                        "appearance_probability": 1.0,
                    }
                )
                pid += 1
    return pd.DataFrame(rows)


def _current(players):
    ids = {1, 7, 2, 3, 8, 9, 14, 16, 17, 22, 23, 28, 24, 30, 36}
    assert len(ids) == 15
    assert set(ids).issubset(set(players.player_id.astype(int)))
    return ids


def test_receding_horizon_recomputes_and_exact_rescores_first_action():
    players = _pool()
    current = _current(players)
    projections = pd.DataFrame(
        [
            {
                "player_id": int(pid),
                "gw": 1,
                "xp": 3.0 + int(pid) / 100,
                "risk_adjusted_xp": 2.0,
            }
            for pid in players.player_id
        ]
    )
    stale_plan = TransferPlan(
        status="Optimal",
        objective=1.0,
        weeks=[{"gw": 1, "transfers": 0, "hit_cost": 0}],
    )
    state = TeamState(squad=current, bank=5.0, free_transfers=1)
    out = analyse_receding_horizon(players, projections, [1], state, stale_plan)
    assert out.status == "optimal"
    assert out.action_now["gw"] == 1
    assert out.projection_col == "xp"
    assert out.optimal_objective != stale_plan.objective
    assert out.roll_objective is not None
    assert out.roll_regret is not None
    assert out.contingent_future == []
    assert out.state_transition_reconciled is True
    assert len(out.canonical_squad or []) == 15
    assert len(out.canonical_xi or []) == 11
    assert out.canonical_captain
    assert out.canonical_vice_captain
    assert out.canonical_captain != out.canonical_vice_captain
    assert out.canonical_expected_points is not None


def test_receding_horizon_handles_empty_gameweek_list_without_projection_table():
    players = _pool()
    current = _current(players)
    state = TeamState(squad=current)
    out = analyse_receding_horizon(players, pd.DataFrame(), [], state, None)
    assert out.status == "unavailable"
    assert out.recommended_action == "none"
