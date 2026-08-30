from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from apex.forecast.dastan_live import (
    aggregate_prediction_rows,
    assert_feature_invariance,
    build_target_player_rows,
    build_target_team_rows,
    mapping_by_fpl_code,
    target_gameweek,
)


def _bootstrap():
    return {
        "total_players": 1000,
        "events": [
            {"id": 1, "deadline_time": "2026-08-21T18:00:00Z"},
            {"id": 2, "deadline_time": "2026-08-28T18:00:00Z"},
        ],
        "teams": [
            {"id": 1, "name": "Coventry City"},
            {"id": 2, "name": "Hull City"},
        ],
        "elements": [
            {
                "id": 10,
                "code": 1001,
                "web_name": "A",
                "team": 1,
                "element_type": 3,
                "selected_by_percent": "20.0",
                "now_cost": 55,
                "ep_next": "4.2",
                "transfers_in_event": 100,
                "transfers_out_event": 40,
                "status": "a",
            },
            {
                "id": 20,
                "code": 1002,
                "web_name": "B",
                "team": 2,
                "element_type": 4,
                "selected_by_percent": "5.0",
                "now_cost": 60,
                "ep_next": None,
                "transfers_in_event": 10,
                "transfers_out_event": 30,
                "status": "d",
            },
        ],
    }


def _fixtures():
    return [
        {
            "id": 200,
            "event": 2,
            "team_h": 1,
            "team_a": 2,
            "kickoff_time": "2026-08-29T14:00:00Z",
        }
    ]


def _club_map():
    return {"Coventry City": "Coventry", "Hull City": "Hull"}


def test_target_gameweek_is_deadline_aware():
    assert target_gameweek(
        _bootstrap(), now=datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
    ) == 2


def test_stable_code_mapping_ignores_unresolved_rows():
    assert mapping_by_fpl_code(
        [
            {"fpl_code": "1001", "understat_id": "55", "mapping_status": "mapped"},
            {"fpl_code": "1002", "understat_id": "", "mapping_status": "unmapped"},
        ]
    ) == {1001: 55}


def test_target_player_rows_use_current_signals_and_reviewed_opponent_identity():
    rows = build_target_player_rows(
        _bootstrap(),
        _fixtures(),
        gameweek=2,
        understat_by_code={1001: 55},
        understat_name_by_fpl_team=_club_map(),
        outcome_marker=123.0,
    ).set_index("element")
    assert rows.loc[10, "understat_id"] == 55
    assert pd.isna(rows.loc[20, "understat_id"])
    assert rows.loc[10, "us_opponent"] == "Hull"
    assert rows.loc[20, "us_opponent"] == "Coventry"
    assert rows.loc[10, "selected"] == 200.0
    assert rows.loc[10, "transfers_balance"] == 60.0
    assert rows.loc[20, "transfers_balance"] == -20.0
    assert rows.loc[10, "minutes"] == 123.0


def test_target_player_rows_fail_closed_without_club_identity():
    with pytest.raises(RuntimeError, match="missing Understat opponent identity"):
        build_target_player_rows(
            _bootstrap(),
            _fixtures(),
            gameweek=2,
            understat_by_code={},
            understat_name_by_fpl_team={"Coventry City": "Coventry"},
            outcome_marker=0.0,
        )


def test_synthetic_team_rows_are_unique_mirrored_pairing_markers():
    rows = build_target_team_rows(
        _bootstrap(),
        _fixtures(),
        gameweek=2,
        understat_name_by_fpl_team=_club_map(),
        sentinel_base=1_000_000,
    ).set_index("understat_team")
    assert rows.loc["Coventry", "scored"] == rows.loc["Hull", "missed"]
    assert rows.loc["Coventry", "missed"] == rows.loc["Hull", "scored"]
    assert rows.loc["Coventry", "xG"] == rows.loc["Hull", "xGA"]
    assert rows.loc["Coventry", "xGA"] == rows.loc["Hull", "xG"]


def test_feature_invariance_rejects_future_placeholder_leakage():
    left = pd.DataFrame([{"fpl_code": 1001, "fixture": 200, "safe": 1.0, "leak": 2.0}])
    right = pd.DataFrame([{"fpl_code": 1001, "fixture": 200, "safe": 1.0, "leak": 9.0}])
    with pytest.raises(RuntimeError, match="future placeholder values leak"):
        assert_feature_invariance(left, right, ["safe", "leak"])


def test_prediction_aggregation_is_one_row_per_official_player():
    predicted = pd.DataFrame(
        [
            {
                "element": 10,
                "xpts": 4.2,
                "expected_minutes": 80.0,
                "p_any": 0.95,
                "p60": 0.85,
            },
            {
                "element": 20,
                "xpts": 3.1,
                "expected_minutes": 70.0,
                "p_any": 0.90,
                "p60": 0.75,
            },
        ]
    )
    rows = aggregate_prediction_rows(predicted, _bootstrap(), _fixtures(), gameweek=2)
    assert [row["player_id"] for row in rows] == [10, 20]
    assert rows[0]["xp"] == 4.2
    assert rows[0]["coverage_status"] == "FORECAST"
