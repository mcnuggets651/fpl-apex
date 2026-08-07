from __future__ import annotations

import pandas as pd
import pytest

from apex_fpl.models.elite import EliteWeights, build_elite_projection_surface


def _players() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": 1,
                "position": "MID",
                "price": 12.0,
                "expected_minutes": 88.0,
                "start_probability": 0.98,
                "appearance_probability": 0.99,
                "shots_per_90": 4.5,
                "big_chances_per_90": 1.2,
            },
            {
                "player_id": 2,
                "position": "MID",
                "price": 5.0,
                "expected_minutes": 72.0,
                "start_probability": 0.78,
                "appearance_probability": 0.90,
                "shots_per_90": 1.1,
                "big_chances_per_90": 0.2,
            },
        ]
    )


def _projections() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": 1,
                "gw": 1,
                "xp": 6.5,
                "xp_attack": 4.4,
                "xp_clean_sheet": 0.3,
                "xp_bonus_prior": 0.7,
                "xp_defensive_contribution": 0.1,
                "xp_set_piece_prior": 0.5,
                "model_xg90": 0.55,
                "model_xa90": 0.35,
                "penalty_share": 1.0,
                "corners_share": 0.5,
                "direct_freekick_share": 0.5,
                "indirect_freekick_share": 0.5,
                "projection_ceiling_80": 10.0,
            },
            {
                "player_id": 2,
                "gw": 1,
                "xp": 4.2,
                "xp_attack": 2.0,
                "xp_clean_sheet": 0.3,
                "xp_bonus_prior": 0.3,
                "xp_defensive_contribution": 0.2,
                "xp_set_piece_prior": 0.0,
                "model_xg90": 0.20,
                "model_xa90": 0.15,
                "penalty_share": 0.0,
                "corners_share": 0.0,
                "direct_freekick_share": 0.0,
                "indirect_freekick_share": 0.0,
                "projection_ceiling_80": 6.0,
            },
        ]
    )


def test_default_weights_sum_to_one() -> None:
    EliteWeights().validate()


def test_invalid_weights_are_rejected() -> None:
    with pytest.raises(ValueError):
        EliteWeights(attack=0.50).validate()


def test_elite_prefers_high_ceiling_premium_over_cheaper_efficiency() -> None:
    out = build_elite_projection_surface(_players(), _projections())
    premium = out.loc[out["player_id"] == 1].iloc[0]
    cheap = out.loc[out["player_id"] == 2].iloc[0]

    assert premium["elite_score"] > cheap["elite_score"]
    assert premium["elite_attack_score"] > cheap["elite_attack_score"]
    assert premium["elite_captaincy_score"] > cheap["elite_captaincy_score"]
    assert premium["elite_value_score"] < cheap["elite_value_score"]
    assert premium["elite_weight_profile"] == "35/20/15/10/10/5/5"


def test_elite_surface_preserves_raw_expected_points() -> None:
    projections = _projections()
    out = build_elite_projection_surface(_players(), projections)
    assert out["xp"].tolist() == projections["xp"].tolist()
