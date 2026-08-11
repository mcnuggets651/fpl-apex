from __future__ import annotations

import numpy as np
import pandas as pd

from apex_fpl.models.projection import _blend_rate, project_players
from apex_fpl.models.tactical import infer_tactical_roles
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


def _projection_player(preseason_xg90):
    return pd.DataFrame(
        [
            {
                "player_id": 1,
                "team": 1,
                "position": "MID",
                "expected_minutes": 90,
                "expected_goals_per_90": 0.60,
                "expected_assists_per_90": 0.20,
                "defensive_contribution_per_90": 0.0,
                "preseason_minutes": 180,
                "preseason_xg90": preseason_xg90,
                "preseason_xa90": np.nan,
                "preseason_defcon90": np.nan,
            }
        ]
    )


def test_projection_preserves_missing_preseason_return_end_to_end():
    fixtures = pd.DataFrame(
        [{"team": 1, "gw": 1, "attack_multiplier": 1.0, "defence_multiplier": 1.0}]
    )
    missing = project_players(_projection_player(np.nan), fixtures, [1]).iloc[0]
    no_preseason = _projection_player(np.nan).drop(
        columns=["preseason_minutes", "preseason_xg90", "preseason_xa90", "preseason_defcon90"]
    )
    baseline = project_players(no_preseason, fixtures, [1]).iloc[0]
    observed_zero = project_players(_projection_player(0.0), fixtures, [1]).iloc[0]

    assert missing["xp_attack"] == baseline["xp_attack"]
    assert observed_zero["xp_attack"] < missing["xp_attack"]


def test_tactical_inference_preserves_missing_preseason_return_end_to_end():
    missing = infer_tactical_roles(_projection_player(np.nan)).iloc[0]
    observed_zero = infer_tactical_roles(_projection_player(0.0)).iloc[0]

    assert missing["tactical_attack_index"] > observed_zero["tactical_attack_index"]
