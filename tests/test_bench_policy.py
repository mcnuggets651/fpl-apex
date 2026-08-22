from __future__ import annotations

import pandas as pd
import pytest

from apex_fpl.optimisation.bench_policy import (
    BenchResilienceError,
    admissible_outfield_orders,
    bench_resilience_ok,
    credible_first_bench_ids,
    playable_outfield_ids,
    require_bench_resilience,
)
from apex_fpl.optimisation.exact_decision import optimise_fixed_squad_gameweek
from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.mechanics import optimise_gameweek_mechanics


def _squad() -> pd.DataFrame:
    rows = []
    pid = 1
    team = 1
    for pos, count in (("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)):
        for _ in range(count):
            rows.append(
                {
                    "player_id": pid,
                    "web_name": f"P{pid}",
                    "team": team,
                    "team_name": f"T{team}",
                    "position": pos,
                    "price": 4.0,
                    "appearance_probability": 0.95,
                    "expected_minutes": 75.0,
                    "start_probability": 0.90,
                }
            )
            pid += 1
            team = 1 + (team % 5)
    return pd.DataFrame(rows)


def test_thresholds_use_governed_or_semantics_and_exclude_goalkeepers():
    players = pd.DataFrame(
        [
            {"player_id": 1, "position": "GK", "appearance_probability": 1.0, "expected_minutes": 90},
            {"player_id": 2, "position": "DEF", "appearance_probability": 0.60, "expected_minutes": 0},
            {"player_id": 3, "position": "MID", "appearance_probability": 0.0, "expected_minutes": 20},
            {"player_id": 4, "position": "FWD", "appearance_probability": 0.70, "expected_minutes": 0},
            {"player_id": 5, "position": "DEF", "appearance_probability": 0.0, "expected_minutes": 30},
            {"player_id": 6, "position": "MID", "appearance_probability": 0.59, "expected_minutes": 19.9},
        ]
    )
    assert playable_outfield_ids(players) == {2, 3, 4, 5}
    assert credible_first_bench_ids(players) == {4, 5}


def test_bench_contract_requires_two_playable_and_a_credible_first_option():
    playable = {6, 7}
    first = {7}
    assert bench_resilience_ok({6, 7, 12}, playable_ids=playable, first_bench_ids=first)
    assert not bench_resilience_ok({6, 8, 12}, playable_ids=playable, first_bench_ids=first)
    assert not bench_resilience_ok({6, 7, 12}, playable_ids={6, 7}, first_bench_ids={99})
    require_bench_resilience({6, 7, 12}, playable_ids=playable, first_bench_ids=first)
    with pytest.raises(BenchResilienceError, match="minimum 2"):
        require_bench_resilience({6, 8, 12}, playable_ids=playable, first_bench_ids=first)


def test_admissible_orders_never_put_an_ineligible_player_first():
    orders = admissible_outfield_orders({6, 7, 12}, first_bench_ids={7, 12})
    assert len(orders) == 4
    assert {order[0] for order in orders} == {7, 12}
    assert all(set(order) == {6, 7, 12} for order in orders)
    with pytest.raises(BenchResilienceError, match="first-autosub"):
        admissible_outfield_orders({6, 7, 12}, first_bench_ids={99})


def test_exact_mechanics_changes_order_instead_of_post_hoc_publication_mutation():
    squad = _squad()
    xi_ids = [1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15]
    xi = squad[squad.player_id.isin(xi_ids)].copy()
    # Bench outfield is 6,7,12. Player 6 has the strongest autosub xP but fails the
    # governed first-bench floor; 7 and 12 are credible.
    squad.loc[squad.player_id.eq(6), ["appearance_probability", "expected_minutes"]] = [0.50, 10.0]
    squad.loc[squad.player_id.eq(7), ["appearance_probability", "expected_minutes"]] = [0.80, 60.0]
    squad.loc[squad.player_id.eq(12), ["appearance_probability", "expected_minutes"]] = [0.75, 55.0]
    xp = {int(pid): 2.0 for pid in squad.player_id}
    xp[6] = 25.0
    xp[7] = 5.0
    xp[12] = 4.0
    appearance = dict(zip(squad.player_id.astype(int), squad.appearance_probability.astype(float)))

    unconstrained = optimise_gameweek_mechanics(squad, xi, xp, appearance)
    constrained = optimise_gameweek_mechanics(
        squad,
        xi,
        xp,
        appearance,
        enforce_current_bench_resilience=True,
    )
    assert unconstrained.outfield_bench_order[0] == 6
    assert constrained.outfield_bench_order[0] in {7, 12}
    assert set(constrained.outfield_bench_order) == {6, 7, 12}


def test_fixed_squad_exact_solver_fails_typed_when_no_resilient_submission_exists():
    squad = _squad()
    squad.loc[:, "appearance_probability"] = 0.10
    squad.loc[:, "expected_minutes"] = 5.0
    # Leave only one outfielder remotely playable; no legal XI can leave two on bench.
    squad.loc[squad.player_id.eq(6), ["appearance_probability", "expected_minutes"]] = [0.90, 70.0]
    xp = {int(pid): 3.0 for pid in squad.player_id}
    appearance = dict(zip(squad.player_id.astype(int), squad.appearance_probability.astype(float)))
    with pytest.raises(BenchResilienceError, match="no submitted XI"):
        optimise_fixed_squad_gameweek(
            squad,
            xp,
            appearance,
            enforce_current_bench_resilience=True,
        )


def test_initial_horizon_milp_and_exact_mechanics_agree_on_resilient_current_submission():
    players = _squad()
    projections = pd.DataFrame(
        [
            {"player_id": int(pid), "gw": 2, "xp": 2.0 + int(pid) / 100.0}
            for pid in players.player_id
        ]
    )
    solution = optimise_initial_horizon(
        players,
        projections,
        [2],
        budget=100.0,
        max_per_team=3,
        projection_col="xp",
        enforce_current_bench_resilience=True,
    )
    assert solution.status == "Optimal"
    assert solution.solver["current_bench_resilience_enforced"] is True
    xp = dict(zip(projections.player_id.astype(int), projections.xp.astype(float)))
    appearance = dict(zip(players.player_id.astype(int), players.appearance_probability.astype(float)))
    _, mechanics = optimise_fixed_squad_gameweek(
        solution.squad,
        xp,
        appearance,
        enforce_current_bench_resilience=True,
    )
    assert mechanics.outfield_bench_order[0] in credible_first_bench_ids(players)
    assert bench_resilience_ok(
        mechanics.outfield_bench_order,
        playable_ids=playable_outfield_ids(players),
        first_bench_ids=credible_first_bench_ids(players),
    )
