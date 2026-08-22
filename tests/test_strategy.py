import pytest
import pandas as pd

from apex_fpl.optimisation.bench_policy import (
    bench_resilience_ok,
    credible_first_bench_ids,
    playable_outfield_ids,
)
from apex_fpl.optimisation.transfers import TransferPlan
from apex_fpl.services.strategy import (
    _reconcile_executable_action,
    analyse_receding_horizon,
)
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
                        "expected_minutes": 75.0,
                    }
                )
                pid += 1
    return pd.DataFrame(rows)


def _current(players):
    ids = {1, 7, 2, 3, 8, 9, 14, 16, 17, 22, 23, 28, 24, 30, 36}
    assert len(ids) == 15
    assert set(ids).issubset(set(players.player_id.astype(int)))
    return ids


def _projections(players: pd.DataFrame, gw: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": int(pid),
                "gw": gw,
                "xp": 3.0 + int(pid) / 100,
                "risk_adjusted_xp": 2.0,
            }
            for pid in players.player_id
        ]
    )


def _ids(rows):
    return [int(row["player_id"]) for row in rows]


def test_receding_horizon_recomputes_and_exact_rescores_first_action():
    players = _pool()
    current = _current(players)
    projections = _projections(players, 2)
    stale_plan = TransferPlan(
        status="Optimal",
        objective=1.0,
        weeks=[{"gw": 2, "transfers": 0, "hit_cost": 0}],
    )
    state = TeamState(squad=current, bank=5.0, free_transfers=1)
    out = analyse_receding_horizon(players, projections, [2], state, stale_plan)
    assert out.status == "optimal"
    assert out.action_now["gw"] == 2
    assert out.projection_col == "xp"
    assert out.optimal_objective != stale_plan.objective
    assert out.roll_objective is not None
    assert out.roll_regret is not None
    assert out.contingent_future == []
    assert out.state_transition_reconciled is True
    assert out.current_bench_resilience_enforced is True
    assert len(out.canonical_squad or []) == 15
    assert len(out.canonical_xi or []) == 11
    assert out.canonical_captain
    assert out.canonical_vice_captain
    assert out.canonical_captain_id is not None
    assert out.canonical_vice_captain_id is not None
    assert out.canonical_captain_id != out.canonical_vice_captain_id
    assert out.canonical_bench_gk_id is not None
    assert len(out.canonical_outfield_bench_order_ids or []) == 3
    assert out.canonical_expected_points is not None

    action = out.action_now or {}
    assert action["mechanics_authority"] == "independent_exact_current_gameweek_rescore"
    assert action["mechanics_reconciled"] is True
    assert _ids(action["xi"]) == _ids(out.canonical_xi or [])
    assert _ids(action["captain"]) == [out.canonical_captain_id]
    assert _ids(action["vice_captain"]) == [out.canonical_vice_captain_id]
    assert int(action["bench_gk"]["player_id"]) == out.canonical_bench_gk_id
    assert _ids(action["outfield_bench_order"]) == out.canonical_outfield_bench_order_ids
    assert action["exact_expected_total_points"] == pytest.approx(out.canonical_expected_points)


def test_executable_action_overwrites_provisional_optimizer_mechanics():
    squad = [
        {"player_id": pid, "web_name": f"P{pid}", "xp": 3.0 + pid / 10}
        for pid in range(1, 16)
    ]
    first = {
        "gw": 2,
        "squad": squad,
        "xi": squad[:11],
        "captain": [squad[0]],
        "vice_captain": [squad[1]],
    }
    canonical_xi = squad[2:13]
    action = _reconcile_executable_action(
        first,
        canonical_squad=squad,
        canonical_xi=canonical_xi,
        captain_id=12,
        vice_id=11,
        bench_gk_id=1,
        bench_order_ids=[2, 14, 15],
        expected_points=55.25,
    )

    assert _ids(action["xi"]) == list(range(3, 14))
    assert _ids(action["captain"]) == [12]
    assert _ids(action["vice_captain"]) == [11]
    assert action["mechanics_reconciled"] is True
    assert action["mechanics_authority"] == "independent_exact_current_gameweek_rescore"
    assert action["exact_expected_total_points"] == pytest.approx(55.25)


def test_executable_action_fails_closed_on_squad_identity_disagreement():
    squad = [{"player_id": pid, "web_name": f"P{pid}"} for pid in range(1, 16)]
    malformed = {"gw": 2, "squad": squad[:-1]}
    with pytest.raises(ValueError, match="does not reconcile"):
        _reconcile_executable_action(
            malformed,
            canonical_squad=squad,
            canonical_xi=squad[:11],
            captain_id=1,
            vice_id=2,
            bench_gk_id=12,
            bench_order_ids=[13, 14, 15],
            expected_points=50.0,
        )


def test_unsafe_roll_is_inadmissible_and_model_self_heals_with_current_transfer():
    players = _pool()
    current = _current(players)
    players.loc[:, "appearance_probability"] = 0.10
    players.loc[:, "expected_minutes"] = 5.0
    players.loc[
        players.player_id.isin([2, 15]),
        ["appearance_probability", "expected_minutes"],
    ] = [0.90, 75.0]
    projections = _projections(players, 2)
    state = TeamState(squad=current, bank=5.0, free_transfers=1)

    out = analyse_receding_horizon(players, projections, [2], state)

    assert out.status == "optimal"
    assert out.roll_admissible is False
    assert out.roll_objective is None
    assert out.roll_regret is None
    assert out.recommended_transfers >= 1
    assert out.recommended_action != "roll"
    assert out.state_transition_reconciled is True
    final_ids = {int(row["player_id"]) for row in out.canonical_squad or []}
    assert 2 in final_ids
    assert 15 in final_ids
    bench_ids = out.canonical_outfield_bench_order_ids or []
    assert bench_resilience_ok(
        bench_ids,
        playable_ids=playable_outfield_ids(players),
        first_bench_ids=credible_first_bench_ids(players),
    )
    assert bench_ids[0] in credible_first_bench_ids(players)


def test_receding_horizon_handles_empty_gameweek_list_without_projection_table():
    players = _pool()
    current = _current(players)
    state = TeamState(squad=current)
    out = analyse_receding_horizon(players, pd.DataFrame(), [], state, None)
    assert out.status == "unavailable"
    assert out.recommended_action == "none"
