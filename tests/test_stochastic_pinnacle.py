import numpy as np
import pandas as pd

from apex_fpl.models.scenarios import ProjectionScenarios, generate_projection_scenarios
from apex_fpl.optimisation.cvar import optimise_initial_cvar


def test_correlated_scenario_generator_links_team_attack_and_opponent_clean_sheet():
    players = pd.DataFrame(
        [
            {"player_id": 1, "team": 1},
            {"player_id": 2, "team": 1},
            {"player_id": 3, "team": 2},
        ]
    )
    projections = pd.DataFrame(
        [
            {
                "player_id": 1,
                "gw": 1,
                "opponent": 2,
                "xp": 6.0,
                "apex_xp": 6.0,
                "projection_sd": 2.0,
                "xp_attack": 5.0,
                "xp_clean_sheet": 0.0,
            },
            {
                "player_id": 2,
                "gw": 1,
                "opponent": 2,
                "xp": 5.0,
                "apex_xp": 5.0,
                "projection_sd": 1.8,
                "xp_attack": 4.2,
                "xp_clean_sheet": 0.0,
            },
            {
                "player_id": 3,
                "gw": 1,
                "opponent": 1,
                "xp": 4.5,
                "apex_xp": 4.5,
                "projection_sd": 1.7,
                "xp_attack": 0.1,
                "xp_clean_sheet": 3.8,
            },
        ]
    )
    scenarios = generate_projection_scenarios(
        players,
        projections,
        [1],
        n_scenarios=2048,
        seed=42,
    )
    values = scenarios.values[:, :, 0]
    same_team_corr = np.corrcoef(values[:, 0], values[:, 1])[0, 1]
    opponent_corr = np.corrcoef(values[:, 0], values[:, 2])[0, 1]
    assert same_team_corr > 0.10
    assert opponent_corr < 0.0
    assert abs(values[:, 0].mean() - 6.0) < 0.35


def test_scenarios_prefer_forecast_uncertainty_over_outcome_variance():
    players = pd.DataFrame([{"player_id": 1, "team": 1}])
    projections = pd.DataFrame(
        [
            {
                "player_id": 1,
                "gw": 1,
                "xp": 6.0,
                "apex_xp": 6.0,
                "projection_sd": 20.0,
                "forecast_uncertainty_sd": 0.10,
            }
        ]
    )
    scenarios = generate_projection_scenarios(
        players,
        projections,
        [1],
        n_scenarios=2048,
        seed=44,
    )
    assert np.std(scenarios.values[:, 0, 0]) < 0.20


def _robust_pool():
    rows = []
    pid = 1
    team = 1
    for pos, count in [("GK", 2), ("MID", 5), ("FWD", 3)]:
        for _ in range(count):
            rows.append(
                {
                    "player_id": pid,
                    "web_name": f"P{pid}",
                    "team": team,
                    "team_name": f"T{team}",
                    "position": pos,
                    "price": 4.0,
                    "gw1_xp": 1.0,
                    "horizon_xp": 1.0,
                    "appearance_probability": 1.0,
                }
            )
            pid += 1
            team = team % 8 + 1
    for _ in range(4):
        rows.append(
            {
                "player_id": pid,
                "web_name": f"P{pid}",
                "team": team,
                "team_name": f"T{team}",
                "position": "DEF",
                "price": 4.0,
                "gw1_xp": 9.0,
                "horizon_xp": 9.0,
                "appearance_probability": 1.0,
            }
        )
        pid += 1
        team = team % 8 + 1
    risky = pid
    rows.append(
        {
            "player_id": risky,
            "web_name": "Risky",
            "team": team,
            "team_name": f"T{team}",
            "position": "DEF",
            "price": 4.0,
            "gw1_xp": 6.0,
            "horizon_xp": 6.0,
            "appearance_probability": 1.0,
        }
    )
    pid += 1
    team = team % 8 + 1
    safe = pid
    rows.append(
        {
            "player_id": safe,
            "web_name": "Safe",
            "team": team,
            "team_name": f"T{team}",
            "position": "DEF",
            "price": 4.0,
            "gw1_xp": 5.5,
            "horizon_xp": 5.5,
            "appearance_probability": 1.0,
        }
    )
    return pd.DataFrame(rows), risky, safe


def _manual_scenarios(players, risky, safe):
    pids = players.player_id.to_numpy(int)
    values = np.zeros((40, len(pids), 1), dtype=float)
    by_id = {int(pid): i for i, pid in enumerate(pids)}
    for pid in pids:
        pos = players.loc[players.player_id == pid, "position"].iloc[0]
        values[:, by_id[int(pid)], 0] = 9.0 if pos == "DEF" and pid not in {risky, safe} else 1.0
    values[:20, by_id[risky], 0] = 0.0
    values[20:, by_id[risky], 0] = 12.0
    values[:, by_id[safe], 0] = 5.5
    return ProjectionScenarios(
        player_ids=pids,
        gameweeks=np.asarray([1]),
        values=values,
        seed=1,
    )


def test_cvar_changes_decision_when_higher_mean_asset_has_bad_downside():
    players, risky, safe = _robust_pool()
    scenarios = _manual_scenarios(players, risky, safe)

    mean_only = optimise_initial_cvar(
        players,
        scenarios,
        budget=100.0,
        decay=1.0,
        bench_weight=0.10,
        cvar_alpha=0.25,
        cvar_weight=0.0,
    )
    robust = optimise_initial_cvar(
        players,
        scenarios,
        budget=100.0,
        decay=1.0,
        bench_weight=0.10,
        cvar_alpha=0.25,
        cvar_weight=0.65,
    )
    assert mean_only.status == "Optimal"
    assert robust.status == "Optimal"
    assert risky in set(mean_only.squad.player_id)
    assert safe not in set(mean_only.squad.player_id)
    assert safe in set(robust.squad.player_id)
    assert risky not in set(robust.squad.player_id)
    assert robust.lower_tail_cvar > mean_only.lower_tail_cvar


def test_cvar_never_captains_an_ineligible_projection_outlier():
    players, risky, safe = _robust_pool()
    scenarios = _manual_scenarios(players, risky, safe)
    scenarios.values[:, scenarios.player_ids == risky, :] = 50.0
    eligible = set(players["player_id"].astype(int)) - {risky}
    solution = optimise_initial_cvar(
        players,
        scenarios,
        budget=100.0,
        decay=1.0,
        cvar_weight=0.0,
        captain_eligible=eligible,
    )
    assert solution.status == "Optimal"
    assert risky not in set(solution.captain["player_id"].astype(int))
