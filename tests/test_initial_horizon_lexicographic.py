from __future__ import annotations

import pandas as pd

from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon


def _players() -> pd.DataFrame:
    positions = (
        ["GK", "GK"]
        + ["DEF"] * 5
        + ["MID"] * 6
        + ["FWD"] * 3
    )
    rows = []
    for pid, position in enumerate(positions, start=1):
        rows.append(
            {
                "player_id": pid,
                "web_name": f"P{pid}",
                "team": pid,
                "team_name": f"T{pid}",
                "position": position,
                "price": 4.5,
                "appearance_probability": 1.0,
            }
        )
    return pd.DataFrame(rows)


def _projections() -> pd.DataFrame:
    rows = []
    # Six midfielders compete for five slots. P8 has slightly better raw xP;
    # P9 has much better secondary utility. An exact xP floor must retain P8.
    xp_by_id = {pid: 5.0 for pid in range(1, 17)}
    xp_by_id[8] = 6.0
    xp_by_id[9] = 5.0
    for pid in range(10, 14):
        xp_by_id[pid] = 10.0

    elite_by_id = {pid: 0.5 for pid in range(1, 17)}
    elite_by_id[8] = 0.01
    elite_by_id[9] = 1.0

    for pid in range(1, 17):
        rows.append(
            {
                "player_id": pid,
                "gw": 1,
                "xp": xp_by_id[pid],
                "elite_score": elite_by_id[pid],
            }
        )
    return pd.DataFrame(rows)


def test_secondary_objective_cannot_break_exact_raw_xp_floor() -> None:
    players = _players()
    projections = _projections()
    primary = optimise_initial_horizon(
        players,
        projections,
        [1],
        projection_col="xp",
        captain_eligible=set(players["player_id"]),
    )
    assert primary.status == "Optimal"

    secondary = optimise_initial_horizon(
        players,
        projections,
        [1],
        projection_col="elite_score",
        reference_projection_col="xp",
        min_reference_objective=primary.objective - 1e-6,
        display_projection_col="xp",
        captain_eligible=set(players["player_id"]),
    )
    assert secondary.status == "Optimal"
    assert set(secondary.squad["player_id"]) == set(primary.squad["player_id"])
    assert 8 in set(secondary.squad["player_id"])
    assert 9 not in set(secondary.squad["player_id"])
    assert secondary.xi["decision_projection_col"].eq("elite_score").all()
    assert secondary.xi["display_projection_col"].eq("xp").all()


def test_secondary_objective_can_choose_near_optimal_alternative_with_relaxed_floor() -> None:
    players = _players()
    projections = _projections()
    primary = optimise_initial_horizon(
        players,
        projections,
        [1],
        projection_col="xp",
        captain_eligible=set(players["player_id"]),
    )
    secondary = optimise_initial_horizon(
        players,
        projections,
        [1],
        projection_col="elite_score",
        reference_projection_col="xp",
        min_reference_objective=primary.objective * 0.95,
        display_projection_col="xp",
        captain_eligible=set(players["player_id"]),
    )
    assert secondary.status == "Optimal"
    assert 9 in set(secondary.squad["player_id"])


def test_xi_ineligible_player_can_remain_in_squad_but_never_start() -> None:
    players = _players()
    players["xi_evidence_eligible"] = True
    players.loc[players.player_id.eq(10), "xi_evidence_eligible"] = False
    solution = optimise_initial_horizon(
        players,
        _projections(),
        [1],
        locked={10},
        captain_eligible=set(players.player_id) - {10},
    )
    assert solution.status == "Optimal"
    assert 10 in set(solution.squad.player_id)
    assert 10 not in set(solution.xi.player_id)
