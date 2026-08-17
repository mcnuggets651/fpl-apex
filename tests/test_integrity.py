import pandas as pd
import pytest

from apex_fpl.services.integrity import reconcile


def test_official_identity_wins_on_club_conflict():
    official = pd.DataFrame(
        [{"player_id": 1, "web_name": "Player", "team": 2, "position": "MID", "price": 7.0}]
    )
    core = pd.DataFrame(
        [{"player_id": 1, "web_name": "Player", "team": 9, "expected_goals_per_90": 0.3}]
    )
    merged, warnings = reconcile(official, core)
    assert merged.iloc[0]["team"] == 2
    assert merged.iloc[0]["expected_goals_per_90"] == 0.3
    assert ((warnings["field"] == "team") & (warnings["external"] == 9)).any()


def test_longitudinal_core_uses_latest_player_gameweek_snapshot():
    official = pd.DataFrame(
        [{"player_id": 1, "web_name": "Player", "team": 2, "position": "MID", "price": 7.0}]
    )
    core = pd.DataFrame(
        [
            {"player_id": 1, "gw": 1, "minutes": 80, "expected_goals_per_90": 0.2},
            {"player_id": 1, "gw": 2, "minutes": 170, "expected_goals_per_90": 0.4},
        ]
    )
    merged, warnings = reconcile(official, core)

    assert len(merged) == 1
    assert merged.iloc[0]["gw"] == 2
    assert merged.iloc[0]["minutes"] == 170
    assert merged.iloc[0]["expected_goals_per_90"] == pytest.approx(0.4)
    assert warnings.empty


def test_longitudinal_core_rejects_ambiguous_duplicate_player_gameweek():
    official = pd.DataFrame(
        [{"player_id": 1, "web_name": "Player", "team": 2, "position": "MID", "price": 7.0}]
    )
    core = pd.DataFrame(
        [
            {"player_id": 1, "gw": 2, "minutes": 160},
            {"player_id": 1, "gw": 2, "minutes": 170},
        ]
    )
    with pytest.raises(ValueError, match="ambiguous duplicate player/GW snapshots"):
        reconcile(official, core)
