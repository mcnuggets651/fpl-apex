from __future__ import annotations

import pandas as pd
import pytest

from apex_fpl.data.tactical import load_tactical_roles
from apex_fpl.models.projection import project_players


def test_verified_set_piece_shares_override_order_prior(tmp_path):
    context = tmp_path / "tactical_roles.csv"
    pd.DataFrame(
        [
            {
                "player_id": 1,
                "tactical_role": "penalty taker",
                "role_multiplier": 1.0,
                "role_confidence": 0.95,
                "penalty_share": 0.8,
                "corners_share": 0.5,
                "direct_freekick_share": 0.6,
                "indirect_freekick_share": 0.4,
            }
        ]
    ).to_csv(context, index=False)
    loaded = load_tactical_roles(context).iloc[0]
    assert loaded["penalty_share"] == pytest.approx(0.8)
    assert loaded["direct_freekick_share"] == pytest.approx(0.6)


def test_projection_carries_auditable_component_breakdown():
    players = pd.DataFrame(
        [
            {
                "player_id": 1,
                "team": 1,
                "position": "MID",
                "expected_minutes": 82,
                "appearance_probability": 0.96,
                "minutes_60_plus_probability": 0.88,
                "expected_goals_per_90": 0.35,
                "expected_assists_per_90": 0.22,
                "role_multiplier": 1.05,
                "penalties_order": 2,
                "corners_and_indirect_freekicks_order": 1,
                "direct_freekicks_order": 2,
                "penalty_share": 0.85,
                "corners_share": 0.70,
                "direct_freekick_share": 0.55,
                "indirect_freekick_share": 0.65,
                "bps": 120,
                "minutes": 900,
                "defensive_contribution_per_90": 8,
            }
        ]
    )
    fixtures = pd.DataFrame(
        [
            {
                "team": 1,
                "gw": 1,
                "opponent": 2,
                "is_home": True,
                "attack_multiplier": 1.1,
                "defence_multiplier": 1.0,
                "clean_sheet_prob": 0.35,
            }
        ]
    )
    row = project_players(players, fixtures, [1]).iloc[0]
    components = [
        "xp_appearance",
        "xp_attack",
        "xp_clean_sheet",
        "xp_defensive_contribution",
        "xp_saves",
        "xp_bonus_prior",
        "xp_set_piece_prior",
    ]
    assert row["apex_xp"] == pytest.approx(sum(float(row[c]) for c in components))
    assert row["penalty_share"] == pytest.approx(0.85)
    assert row["corners_share"] == pytest.approx(0.70)
    assert row["xp_set_piece_prior"] > 0
