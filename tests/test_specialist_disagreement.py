import pandas as pd

from apex_fpl.services.specialist_disagreement import build_specialist_disagreement_report


def players():
    return pd.DataFrame(
        [
            {
                "player_id": 1,
                "web_name": "HighApex",
                "team_name": "A",
                "position": "DEF",
                "expected_minutes": 82.0,
                "start_probability": 0.90,
            },
            {
                "player_id": 2,
                "web_name": "LowApex",
                "team_name": "B",
                "position": "MID",
                "expected_minutes": 34.0,
                "start_probability": 0.30,
            },
        ]
    )


def test_two_specialists_benching_high_apex_start_is_high_priority():
    predictions = pd.DataFrame(
        [
            {"player_id": 1, "source": "fantasy_football_scout", "predicted_start": False},
            {"player_id": 1, "source": "allaboutfpl", "predicted_start": False},
        ]
    )
    out = build_specialist_disagreement_report(players(), predictions)
    row = out[out.player_id.eq(1)].iloc[0]
    assert row.specialist_consensus == "bench"
    assert row.review_priority == "high"


def test_two_specialists_starting_low_apex_start_is_high_priority():
    predictions = pd.DataFrame(
        [
            {"player_id": 2, "source": "fantasy_football_scout", "predicted_start": True},
            {"player_id": 2, "source": "allaboutfpl", "predicted_start": True},
        ]
    )
    out = build_specialist_disagreement_report(players(), predictions)
    row = out[out.player_id.eq(2)].iloc[0]
    assert row.specialist_consensus == "start"
    assert row.review_priority == "high"


def test_single_specialist_only_flags_sensitive_player_medium():
    predictions = pd.DataFrame(
        [{"player_id": 1, "source": "fantasy_football_scout", "predicted_start": False}]
    )
    normal = build_specialist_disagreement_report(players(), predictions)
    sensitive = build_specialist_disagreement_report(
        players(), predictions, optimiser_sensitive_ids={1}
    )
    assert normal[normal.player_id.eq(1)].iloc[0].review_priority == "none"
    assert sensitive[sensitive.player_id.eq(1)].iloc[0].review_priority == "medium"


def test_specialist_report_is_diagnostic_and_does_not_modify_apex_inputs():
    base = players()
    original = base.copy(deep=True)
    predictions = pd.DataFrame(
        [
            {"player_id": 1, "source": "fantasy_football_scout", "predicted_start": False},
            {"player_id": 1, "source": "allaboutfpl", "predicted_start": False},
        ]
    )
    build_specialist_disagreement_report(base, predictions)
    pd.testing.assert_frame_equal(base, original)
