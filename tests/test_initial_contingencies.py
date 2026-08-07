import pandas as pd

from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.services.initial_plan import (
    build_initial_squad_contingencies,
    initial_chip_policy,
)


def _pool() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    pid = 1
    for team in range(1, 9):
        for position, count in (("GK", 1), ("DEF", 2), ("MID", 2), ("FWD", 1)):
            for _ in range(count):
                rows.append(
                    {
                        "player_id": pid,
                        "web_name": f"P{pid}",
                        "team_name": f"T{team}",
                        "team": team,
                        "position": position,
                        "price": 4.5,
                    }
                )
                pid += 1
    players = pd.DataFrame(rows)
    projections = pd.DataFrame(
        [
            {
                "player_id": int(player_id),
                "gw": gw,
                "xp": 2.0 + int(player_id) / 100 + gw / 20,
                "risk_adjusted_xp": 2.0 + int(player_id) / 100 + gw / 20,
            }
            for player_id in players["player_id"]
            for gw in range(1, 6)
        ]
    )
    return players, projections


def test_initial_squad_route_is_optimal_but_explicitly_contingent():
    players, projections = _pool()
    gameweeks = [1, 2, 3, 4, 5]
    squad = optimise_initial_horizon(players, projections, gameweeks)
    route = build_initial_squad_contingencies(
        squad,
        players,
        projections,
        gameweeks,
        budget=100.0,
        max_per_team=3,
        decay=0.90,
    )
    assert route["status"] == "Optimal"
    assert route["future_moves_are_contingent"] is True
    assert [week["gw"] for week in route["weeks"]] == [2, 3, 4, 5]
    assert all(week["chip"] is None for week in route["weeks"])


def test_initial_chip_policy_does_not_claim_an_uncalibrated_chip_edge():
    policy = initial_chip_policy([1, 2, 3, 4, 5])
    assert policy["status"] == "hold"
    assert policy["recommended_chip"] is None
    assert set(policy["rules"]) == {
        "wildcard",
        "free_hit",
        "bench_boost",
        "triple_captain",
    }
