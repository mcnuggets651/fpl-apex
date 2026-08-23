from types import SimpleNamespace

import pandas as pd

import apex_fpl.optimisation.transfers as transfers
from apex_fpl.optimisation.transfers import _next_ft, optimise_transfer_plan


def _pool():
    rows = []
    pid = 1
    for team in range(1, 9):
        for pos, count in [("GK", 1), ("DEF", 2), ("MID", 2), ("FWD", 1)]:
            for j in range(count):
                rows.append({
                    "player_id": pid,
                    "web_name": f"P{pid}",
                    "team_name": f"T{team}",
                    "team": team,
                    "position": pos,
                    "price": 4.0 + (pid % 4) * 0.5,
                    "horizon_xp": 20 + pid / 10,
                })
                pid += 1
    return pd.DataFrame(rows)


def _legal_current(players: pd.DataFrame) -> set[int]:
    current: set[int] = set()
    for pos, need in {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}.items():
        current.update(players[players.position == pos].head(need).player_id.astype(int))
    return current


def _projections(players: pd.DataFrame, gws=(1,)) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "player_id": int(r.player_id),
            "gw": gw,
            "risk_adjusted_xp": 2.0 + r.player_id / 20 + gw / 10,
        }
        for _, r in players.iterrows()
        for gw in gws
    ])


def test_ft_transition_rule():
    assert _next_ft(1, 0) == 2
    assert _next_ft(5, 0) == 5
    assert _next_ft(3, 1) == 3
    assert _next_ft(3, 3) == 1
    assert _next_ft(2, 4) == 1


def test_multiweek_transfer_plan_is_legal():
    players = _pool()
    current = _legal_current(players)
    gws = [1, 2]
    proj = _projections(players, gws)
    plan = optimise_transfer_plan(players, proj, gws, current, bank=20.0, free_transfers=2, candidate_limit=60)
    assert plan.status == "Optimal"
    assert len(plan.weeks) == 2
    for week in plan.weeks:
        squad = pd.DataFrame(week["squad"])
        xi = pd.DataFrame(week["xi"])
        assert len(squad) == 15
        assert len(xi) == 11
        assert len(week["captain"]) == 1
        assert len(week["vice_captain"]) == 1
        assert week["vice_captain"][0]["player_id"] != week["captain"][0]["player_id"]
        assert (squad.groupby("team_name").size() <= 3).all()
        assert squad.position.value_counts().to_dict() == {"MID": 5, "DEF": 5, "FWD": 3, "GK": 2}


def test_first_gameweek_transfer_bounds_create_exact_counterfactuals():
    players = _pool()
    current = _legal_current(players)
    projections = _projections(players)

    rolled = optimise_transfer_plan(
        players,
        projections,
        [1],
        current,
        bank=20.0,
        candidate_limit=60,
        first_gw_min_transfers=0,
        first_gw_max_transfers=0,
    )
    exact_two = optimise_transfer_plan(
        players,
        projections,
        [1],
        current,
        bank=20.0,
        candidate_limit=60,
        first_gw_min_transfers=2,
        first_gw_max_transfers=2,
    )

    assert rolled.status == "Optimal"
    assert rolled.weeks[0]["transfers"] == 0
    assert exact_two.status == "Optimal"
    assert exact_two.weeks[0]["transfers"] == 2
    assert exact_two.objective <= optimise_transfer_plan(
        players, projections, [1], current, bank=20.0, candidate_limit=60
    ).objective + 1e-6


def test_first_gameweek_transfer_bounds_reject_malformed_ranges():
    players = _pool()
    current = _legal_current(players)
    projections = _projections(players)

    invalid = optimise_transfer_plan(
        players,
        projections,
        [1],
        current,
        bank=20.0,
        candidate_limit=60,
        first_gw_min_transfers=3,
        first_gw_max_transfers=2,
    )
    fractional = optimise_transfer_plan(
        players,
        projections,
        [1],
        current,
        bank=20.0,
        candidate_limit=60,
        first_gw_max_transfers=1.5,
    )

    assert invalid.status == "InputError"
    assert "cannot exceed" in str(invalid.solver_message)
    assert fractional.status == "InputError"
    assert "integer between 0 and 15" in str(fractional.solver_message)


def test_transfer_plan_never_captains_ineligible_projection_outlier():
    players = _pool()
    current = _legal_current(players)
    outlier = int(players.player_id.max())
    projections = pd.DataFrame(
        [
            {
                "player_id": int(pid),
                "gw": 1,
                "risk_adjusted_xp": 100.0 if int(pid) == outlier else 3.0,
            }
            for pid in players.player_id
        ]
    )
    eligible = set(players.player_id.astype(int)) - {outlier}
    plan = optimise_transfer_plan(
        players,
        projections,
        [1],
        current,
        bank=20.0,
        candidate_limit=60,
        captain_eligible=eligible,
    )
    assert plan.status == "Optimal"
    assert plan.weeks[0]["captain"][0]["player_id"] in eligible
    assert plan.weeks[0]["vice_captain"][0]["player_id"] in eligible


def test_solver_limit_is_not_reported_as_infeasible(monkeypatch):
    players = _pool()
    current = _legal_current(players)
    projections = pd.DataFrame(
        [
            {"player_id": int(pid), "gw": 1, "risk_adjusted_xp": 3.0}
            for pid in players.player_id
        ]
    )

    fake_result = SimpleNamespace(
        success=False,
        status=1,
        x=None,
        fun=-100.0,
        message="Time limit reached",
        mip_dual_bound=-105.0,
        mip_gap=0.05,
    )
    monkeypatch.setattr(transfers, "milp", lambda **kwargs: fake_result)

    plan = transfers.optimise_transfer_plan(
        players,
        projections,
        [1],
        current,
        bank=20.0,
        candidate_limit=60,
        solver_time_limit=0.1,
    )

    assert plan.status == "SolverLimit"
    assert plan.solver_status_code == 1
    assert plan.objective == 100.0
    assert plan.objective_upper_bound == 105.0
    assert plan.mip_gap == 0.05
