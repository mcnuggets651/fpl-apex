from __future__ import annotations

import numpy as np
import pandas as pd

from apex_fpl.models.projection import project_players
from apex_fpl.services.statistical_truth import audit_statistical_truth


def _fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "team": 1,
                "gw": 1,
                "opponent": 2,
                "is_home": True,
                "attack_multiplier": 1.0,
                "defence_multiplier": 1.0,
                "clean_sheet_prob": 0.30,
            }
        ]
    )


def _players(**extra) -> pd.DataFrame:
    row = {
        "player_id": 1,
        "web_name": "Test",
        "team": 1,
        "team_name": "Example",
        "position": "MID",
        "price": 6.0,
        "status": "a",
        "expected_minutes": 75.0,
        "appearance_probability": 0.90,
        "start_probability": 0.80,
        "expected_goals_per_90": 0.30,
        "expected_assists_per_90": 0.20,
        "role_multiplier": 1.0,
        "tactical_role": "advanced midfielder",
        "tactical_role_source": "statistical_inference",
        "role_confidence": 0.65,
        "minutes_confidence": 0.70,
    }
    row.update(extra)
    return pd.DataFrame([row])


def _projections(players: pd.DataFrame) -> pd.DataFrame:
    projections = project_players(players, _fixture(), [1])
    projections["source_present_airsenal"] = True
    return projections


def test_statistical_truth_accepts_finite_complete_surface() -> None:
    players = _players()
    payload = audit_statistical_truth(players, _projections(players), expected_players=1)

    assert payload["contract"] == "apex-statistical-truth-v1"
    assert payload["ready"] is True
    assert payload["player_count"] == 1
    assert payload["canonical_projection_pair_coverage"] == 1.0
    assert payload["role_provenance_counts"] == {"statistical_inference": 1}


def test_statistical_truth_blocks_non_finite_player_fields() -> None:
    players = _players(expected_minutes=np.inf)
    payload = audit_statistical_truth(players, _projections(_players()), expected_players=1)

    assert payload["ready"] is False
    assert any("non-finite player statistical fields" in row for row in payload["blockers"])


def test_statistical_truth_blocks_negative_canonical_xp() -> None:
    players = _players()
    projections = _projections(players)
    projections.loc[:, "xp"] = -0.01
    payload = audit_statistical_truth(players, projections, expected_players=1)

    assert payload["ready"] is False
    assert any("canonical projection contains invalid values" in row for row in payload["blockers"])


def test_unknown_role_provenance_is_explicit_warning_not_fact() -> None:
    players = _players(tactical_role_source="unknown")
    payload = audit_statistical_truth(players, _projections(players), expected_players=1)

    assert payload["ready"] is True
    assert payload["role_provenance_counts"] == {"unknown": 1}
    assert any("unknown tactical-role provenance" in row for row in payload["warnings"])
