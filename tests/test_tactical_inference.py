from __future__ import annotations

import pandas as pd

from apex_fpl.models.tactical import infer_tactical_roles


def test_attacking_defender_gets_positive_role_prior():
    players = pd.DataFrame(
        [
            {
                "player_id": 1,
                "position": "DEF",
                "minutes": 900,
                "expected_goals_per_90": 0.12,
                "expected_assists_per_90": 0.24,
                "touches_opposition_box": 65,
                "chances_created": 25,
                "accurate_crosses": 18,
                "defensive_contribution_per_90": 7,
            },
            {
                "player_id": 2,
                "position": "DEF",
                "minutes": 900,
                "expected_goals_per_90": 0.03,
                "expected_assists_per_90": 0.02,
                "touches_opposition_box": 5,
                "chances_created": 2,
                "accurate_crosses": 0,
                "defensive_contribution_per_90": 11,
            },
        ]
    )
    roles = infer_tactical_roles(players).set_index("player_id")
    assert "attacking" in roles.loc[1, "inferred_tactical_role"]
    assert roles.loc[1, "inferred_role_multiplier"] > 1.0
    assert roles.loc[2, "inferred_role_multiplier"] <= 1.0


def test_holding_midfielder_is_not_scored_like_an_advanced_midfielder():
    players = pd.DataFrame(
        [
            {
                "player_id": 10,
                "position": "MID",
                "minutes": 1200,
                "expected_goals_per_90": 0.04,
                "expected_assists_per_90": 0.04,
                "touches_opposition_box": 10,
                "chances_created": 4,
                "defensive_contribution_per_90": 12,
            },
            {
                "player_id": 11,
                "position": "MID",
                "minutes": 1200,
                "expected_goals_per_90": 0.42,
                "expected_assists_per_90": 0.22,
                "touches_opposition_box": 110,
                "chances_created": 35,
                "defensive_contribution_per_90": 3,
            },
        ]
    )
    roles = infer_tactical_roles(players).set_index("player_id")
    assert "holding" in roles.loc[10, "inferred_tactical_role"]
    assert roles.loc[10, "inferred_role_multiplier"] < 1.0
    assert "advanced" in roles.loc[11, "inferred_tactical_role"]
    assert roles.loc[11, "inferred_role_multiplier"] > 1.0


def test_inference_confidence_is_capped_below_verified_override_level():
    players = pd.DataFrame(
        [
            {
                "player_id": 20,
                "position": "FWD",
                "minutes": 3000,
                "expected_goals_per_90": 0.65,
                "expected_assists_per_90": 0.12,
            }
        ]
    )
    role = infer_tactical_roles(players).iloc[0]
    assert role["inferred_tactical_role"] == "central striker"
    assert role["inferred_role_confidence"] <= 0.80
