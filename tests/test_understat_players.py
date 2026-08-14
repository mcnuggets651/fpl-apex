from __future__ import annotations

import numpy as np
import pandas as pd

from apex_fpl.evaluation.understat_players import (
    calibrate_understat_player_blend,
    latest_core_player_rates,
    match_core_understat,
    normalise_player_name,
    normalise_understat_players,
)


def test_understat_player_normalisation_and_rates():
    payload = {
        "players": [
            {
                "id": "1740",
                "player_name": "Paul Pogba",
                "team_title": "Manchester United",
                "time": "900",
                "goals": "5",
                "xG": "6.0",
                "assists": "4",
                "xA": "5.0",
                "shots": "30",
                "key_passes": "25",
                "npxG": "4.5",
                "xGChain": "10.0",
                "xGBuildup": "6.0",
            }
        ]
    }
    frame = normalise_understat_players(payload, 2025)
    assert frame.loc[0, "understat_player_id"] == 1740
    assert frame.loc[0, "understat_xg90"] == 0.6
    assert frame.loc[0, "understat_xa90"] == 0.5
    assert normalise_player_name("João Pedro") == "joaopedro"


def test_core_identity_bridge_rejects_ambiguous_names():
    stats = pd.DataFrame(
        {
            "player_id": [1, 2],
            "gw": [38, 38],
            "expected_goals_per_90": [0.3, 0.4],
            "expected_assists_per_90": [0.2, 0.1],
            "minutes": [2000, 1800],
        }
    )
    players = pd.DataFrame(
        {
            "player_id": [1, 2],
            "first_name": ["Alpha", "Beta"],
            "second_name": ["One", "Two"],
        }
    )
    core = latest_core_player_rates(stats, players, 2024)
    understat = pd.DataFrame(
        {
            "name_key": ["alphaone", "betatwo"],
            "understat_player_id": [11, 12],
            "understat_xg90": [0.35, 0.45],
            "understat_xa90": [0.22, 0.12],
            "minutes": [1900, 1700],
            "goals": [7, 8],
            "assists": [5, 3],
            "actual_goals90": [0.33, 0.42],
            "actual_assists90": [0.24, 0.16],
        }
    )
    matched = match_core_understat(core, understat)
    assert set(matched["player_id"]) == {1, 2}


def test_calibration_promotes_only_supported_understat_signal():
    rng = np.random.default_rng(42)
    rows = []
    for player in range(240):
        truth_g = rng.uniform(0.08, 0.75)
        truth_a = rng.uniform(0.04, 0.45)
        core_g = max(0.01, truth_g + rng.normal(0, 0.18))
        core_a = max(0.01, truth_a + rng.normal(0, 0.14))
        under_g = max(0.01, truth_g + rng.normal(0, 0.07))
        under_a = max(0.01, truth_a + rng.normal(0, 0.06))
        minutes = 1800.0
        rows.append(
            {
                "player_id": player,
                "audit_split": "holdout" if player % 2 == 0 else "calibration",
                "core_xg90": core_g,
                "core_xa90": core_a,
                "understat_xg90": under_g,
                "understat_xa90": under_a,
                "target_minutes": minutes,
                "target_goals": rng.poisson(truth_g * minutes / 90.0),
                "target_assists": rng.poisson(truth_a * minutes / 90.0),
            }
        )
    audit = calibrate_understat_player_blend(
        pd.DataFrame(rows),
        bootstrap_samples=1000,
    )
    assert audit.selected_xg_weight > 0
    assert audit.selected_xa_weight > 0
    assert audit.holdout["rows"] == 120
    assert audit.pass_gate
