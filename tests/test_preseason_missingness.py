from __future__ import annotations

import numpy as np
import pandas as pd

from apex_fpl.models.projection import _blend_rate
from apex_fpl.services.enrichment import add_preseason_features


def test_missing_preseason_return_is_not_converted_to_measured_zero():
    players = pd.DataFrame({"player_id": [1]})
    friendlies = pd.DataFrame(
        [
            {
                "player_id": 1,
                "match_id": 10,
                "minutes_played": 68,
                "start_min": 0,
                "xg": np.nan,
                "xa": np.nan,
                "defensive_contributions": np.nan,
            }
        ]
    )
    out = add_preseason_features(players, friendlies).iloc[0]
    assert out["preseason_minutes"] == 68
    assert pd.isna(out["preseason_xg90"])
    assert not bool(out["preseason_xg_observed"])


def test_missing_preseason_rate_cannot_pull_down_historical_rate():
    result = _blend_rate(
        pd.Series([0.60]),
        pd.Series([np.nan]),
        pd.Series([180.0]),
    )
    assert result.iloc[0] == 0.60


def test_observed_preseason_zero_remains_valid_evidence():
    result = _blend_rate(
        pd.Series([0.60]),
        pd.Series([0.0]),
        pd.Series([180.0]),
    )
    assert result.iloc[0] < 0.60
