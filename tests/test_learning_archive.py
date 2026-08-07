import pandas as pd

from apex_fpl.services.learning import (
    aggregate_deadline_forecast,
    attach_actual_points,
    build_learning_report,
)


def test_deadline_archive_aggregates_dgw_fixture_rows_to_one_player_gw():
    projections = pd.DataFrame(
        [
            {"player_id": 1, "gw": 5, "apex_xp": 3.0, "official_xp": 4.0, "airsenal_xp": 5.0, "xp": 4.0, "projection_sd": 1.0},
            {"player_id": 1, "gw": 5, "apex_xp": 2.0, "official_xp": 4.0, "airsenal_xp": 5.0, "xp": 3.0, "projection_sd": 2.0},
        ]
    )
    # The ensemble layer would already have split full-GW experts across the two
    # fixture rows; emulate that contract here.
    projections["official_xp"] /= 2
    projections["airsenal_xp"] /= 2
    players = pd.DataFrame(
        [{"player_id": 1, "web_name": "P1", "position": "MID", "price": 7.0, "expected_minutes": 85}]
    )
    out = aggregate_deadline_forecast(
        projections,
        players,
        5,
        generated_at="2026-09-01T10:00:00+00:00",
        snapshot_id="abc",
    )
    assert len(out) == 1
    assert out.iloc[0].apex_xp == 5.0
    assert out.iloc[0].official_xp == 4.0
    assert out.iloc[0].airsenal_xp == 5.0
    assert abs(out.iloc[0].projection_sd - (5 ** 0.5)) < 1e-9


def test_actuals_are_attached_only_from_explicit_official_points_map():
    frame = pd.DataFrame([{"player_id": 1, "gw": 1}, {"player_id": 2, "gw": 1}])
    out = attach_actual_points(frame, {1: 9.0, 2: 2.0}, retrieved_at="now")
    assert out.event_points.tolist() == [9.0, 2.0]
    assert out.actuals_retrieved_at.tolist() == ["now", "now"]


def test_learning_report_refuses_to_invent_calibration_before_outcomes_exist():
    report = build_learning_report(pd.DataFrame())
    assert report.completed_gameweeks == []
    assert report.candidate_calibration is None
    assert report.holdout_validation is None
