from __future__ import annotations

import pandas as pd

from apex_fpl.models.bonus import expected_bonus_proxy


def test_2026_bonus_prior_prefers_attacking_fullback_over_defence_only_cb():
    df = pd.DataFrame(
        [
            {
                "position": "DEF",
                "tactical_role": "attacking full-back / wing-back",
                "minutes": 900,
                "bps": 180,
                "saves_per_90": 0,
            },
            {
                "position": "DEF",
                "tactical_role": "central / defensive defender",
                "minutes": 900,
                "bps": 180,
                "saves_per_90": 0,
            },
        ]
    )
    share = pd.Series([1.0, 1.0])
    xg = pd.Series([0.12, 0.05])
    xa = pd.Series([0.22, 0.03])
    defensive = pd.Series([7.0, 11.0])
    bonus = expected_bonus_proxy(df, share, xg, xa, defensive)
    assert bonus.iloc[0] > bonus.iloc[1]


def test_2026_bonus_prior_rewards_goalkeeper_save_volume():
    df = pd.DataFrame(
        [
            {
                "position": "GK",
                "tactical_role": "goalkeeper",
                "minutes": 900,
                "bps": 150,
                "saves_per_90": 5.5,
            },
            {
                "position": "GK",
                "tactical_role": "goalkeeper",
                "minutes": 900,
                "bps": 150,
                "saves_per_90": 1.5,
            },
        ]
    )
    share = pd.Series([1.0, 1.0])
    zeros = pd.Series([0.0, 0.0])
    bonus = expected_bonus_proxy(df, share, zeros, zeros, zeros)
    assert bonus.iloc[0] > bonus.iloc[1]
