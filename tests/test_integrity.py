import pandas as pd
import pytest

from apex_fpl.services.integrity import reconcile


def test_core_club_conflict_with_identity_witness_fails_closed():
    official = pd.DataFrame([{"player_id": 1, "web_name": "Player", "team": 2, "position": "MID", "price": 7.0}])
    core = pd.DataFrame([{"player_id": 1, "web_name": "Player", "team": 9, "expected_goals_per_90": 0.3}])
    with pytest.raises(ValueError, match="identity integrity failed"):
        reconcile(official, core)


def test_core_wrong_name_on_valid_id_fails_closed():
    official = pd.DataFrame([{"player_id": 1, "web_name": "Coyle", "team": 2, "position": "DEF", "price": 4.5}])
    core = pd.DataFrame([{"player_id": 1, "web_name": "Gabriel", "expected_goals_per_90": 0.3}])
    with pytest.raises(ValueError, match="name conflict"):
        reconcile(official, core)


def test_core_full_name_disambiguates_duplicate_web_name():
    official = pd.DataFrame([
        {"player_id": 565, "web_name": "M.Sangaré", "first_name": "Mamadou", "second_name": "Sangaré", "team": 1, "position": "MID", "price": 5.0},
        {"player_id": 488, "web_name": "I.Sangaré", "first_name": "Ibrahim", "second_name": "Sangaré", "team": 2, "position": "MID", "price": 5.0},
    ])
    core = pd.DataFrame([
        {"player_id": 565, "web_name": "Sangaré", "first_name": "Mamadou", "second_name": "Sangaré", "expected_goals_per_90": 0.31},
        {"player_id": 488, "web_name": "Sangaré", "first_name": "Ibrahim", "second_name": "Sangaré", "expected_goals_per_90": 0.12},
    ])
    merged, warnings = reconcile(official, core)
    assert warnings.empty
    assert merged.set_index("player_id").loc[565, "expected_goals_per_90"] == pytest.approx(0.31)
    assert merged.set_index("player_id").loc[488, "expected_goals_per_90"] == pytest.approx(0.12)
    assert merged.set_index("player_id").loc[565, "source_full_name"] == "Mamadou Sangaré"
    assert merged.set_index("player_id").loc[488, "source_full_name"] == "Ibrahim Sangaré"


def test_core_full_name_still_rejects_wrong_id():
    official = pd.DataFrame([
        {"player_id": 565, "web_name": "M.Sangaré", "first_name": "Mamadou", "second_name": "Sangaré", "team": 1, "position": "MID", "price": 5.0},
        {"player_id": 488, "web_name": "I.Sangaré", "first_name": "Ibrahim", "second_name": "Sangaré", "team": 2, "position": "MID", "price": 5.0},
    ])
    core = pd.DataFrame([{"player_id": 565, "web_name": "Sangaré", "first_name": "Ibrahim", "second_name": "Sangaré"}])
    with pytest.raises(ValueError, match="name conflict"):
        reconcile(official, core)


def test_core_identity_witness_is_retained_for_sealed_audit():
    official = pd.DataFrame([{"player_id": 1, "web_name": "Coyle", "first_name": "Lewie", "second_name": "Coyle", "team": 2, "team_name": "Hull", "position": "DEF", "price": 4.5}])
    core = pd.DataFrame([{"player_id": 1, "web_name": "Coyle", "first_name": "Lewie", "second_name": "Coyle", "team": 2, "team_name": "Hull", "position": "DEF", "expected_goals_per_90": 0.3}])
    merged, warnings = reconcile(official, core)
    assert warnings.empty
    assert merged.iloc[0]["web_name_core"] == "Coyle"
    assert merged.iloc[0]["first_name_core"] == "Lewie"
    assert merged.iloc[0]["second_name_core"] == "Coyle"
    assert merged.iloc[0]["team_core"] == 2
    assert merged.iloc[0]["position_core"] == "DEF"
    assert merged.iloc[0]["expected_goals_per_90"] == pytest.approx(0.3)


def test_longitudinal_core_uses_latest_player_gameweek_snapshot():
    official = pd.DataFrame([{"player_id": 1, "web_name": "Player", "team": 2, "position": "MID", "price": 7.0}])
    core = pd.DataFrame([
        {"player_id": 1, "gw": 1, "minutes": 80, "expected_goals_per_90": 0.2},
        {"player_id": 1, "gw": 2, "minutes": 170, "expected_goals_per_90": 0.4},
    ])
    merged, warnings = reconcile(official, core)
    assert len(merged) == 1
    assert merged.iloc[0]["gw"] == 2
    assert merged.iloc[0]["minutes"] == 170
    assert merged.iloc[0]["expected_goals_per_90"] == pytest.approx(0.4)
    assert warnings.empty


def test_longitudinal_core_rejects_ambiguous_duplicate_player_gameweek():
    official = pd.DataFrame([{"player_id": 1, "web_name": "Player", "team": 2, "position": "MID", "price": 7.0}])
    core = pd.DataFrame([
        {"player_id": 1, "gw": 2, "minutes": 160},
        {"player_id": 1, "gw": 2, "minutes": 170},
    ])
    with pytest.raises(ValueError, match="ambiguous duplicate player/GW snapshots"):
        reconcile(official, core)
