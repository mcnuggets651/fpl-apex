import pandas as pd

from apex_fpl.services.integrity import reconcile


def test_official_identity_wins_on_club_conflict():
    official = pd.DataFrame([{"player_id": 1, "web_name": "Player", "team": 2, "position": "MID", "price": 7.0}])
    core = pd.DataFrame([{"player_id": 1, "web_name": "Player", "team": 9, "expected_goals_per_90": .3}])
    merged, warnings = reconcile(official, core)
    assert merged.iloc[0]["team"] == 2
    assert merged.iloc[0]["expected_goals_per_90"] == .3
    assert ((warnings["field"] == "team") & (warnings["external"] == 9)).any()
