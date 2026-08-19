from __future__ import annotations

import numpy as np
import pandas as pd

from apex_fpl.services.statistical_truth import audit_statistical_truth


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
        "role_multiplier": 1.0,
        "tactical_role": "advanced midfielder",
        "tactical_role_source": "statistical_inference",
        "role_confidence": 0.65,
        "minutes_confidence": 0.70,
        "previous_minutes": 180.0,
        "previous_starts": 2.0,
        "previous_appearances": 4.0,
        "previous_role_games": 5.0,
        "preseason_minutes": 135.0,
        "preseason_starts": 2.0,
        "preseason_appearances": 2.0,
        "preseason_recency_evidence": 1.5,
        "xg90_context_reliability": 180.0 / 270.0,
        "xa90_context_reliability": 180.0 / 270.0,
        "xg90_low_sample_adjusted": True,
        "xa90_low_sample_adjusted": False,
    }
    row.update(extra)
    return pd.DataFrame([row])


def _projections() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": 1,
                "gw": 1,
                "xp": 5.0,
                "xp_set_piece_prior": 0.0,
                "source_present_airsenal": True,
            }
        ]
    )


def test_statistical_truth_accepts_finite_complete_surface() -> None:
    players = _players()
    payload = audit_statistical_truth(players, _projections(), expected_players=1)

    assert payload["contract"] == "apex-statistical-truth-v1"
    assert payload["ready"] is True
    assert payload["player_count"] == 1
    assert payload["canonical_projection_pair_coverage"] == 1.0
    assert payload["role_provenance_counts"] == {"statistical_inference": 1}
    assert payload["historical_sample_classes"] == {"low_sample_prior": 1}
    assert payload["preseason_sample_classes"] == {"two_preseason_appearances": 1}
    assert payload["low_sample_attack_adjusted_player_ids"] == [1]
    assert payload["players"][0]["xg90_low_sample_adjusted"] is True


def test_statistical_truth_blocks_non_finite_player_fields() -> None:
    players = _players(expected_minutes=np.inf)
    payload = audit_statistical_truth(players, _projections(), expected_players=1)

    assert payload["ready"] is False
    assert any("non-finite player statistical fields" in row for row in payload["blockers"])


def test_statistical_truth_blocks_negative_canonical_xp() -> None:
    players = _players()
    projections = _projections()
    projections.loc[:, "xp"] = -0.01
    payload = audit_statistical_truth(players, projections, expected_players=1)

    assert payload["ready"] is False
    assert any("canonical projection contains invalid values" in row for row in payload["blockers"])


def test_unknown_role_provenance_is_explicit_warning_not_fact() -> None:
    players = _players(tactical_role_source="unknown")
    payload = audit_statistical_truth(players, _projections(), expected_players=1)

    assert payload["ready"] is True
    assert payload["role_provenance_counts"] == {"unknown": 1}
    assert any("unknown tactical-role provenance" in row for row in payload["warnings"])


def test_zero_history_and_no_preseason_are_uncertainty_not_blockers() -> None:
    players = _players(
        previous_minutes=0.0,
        previous_starts=0.0,
        previous_appearances=0.0,
        previous_role_games=0.0,
        preseason_minutes=0.0,
        preseason_starts=0.0,
        preseason_appearances=0.0,
        preseason_recency_evidence=0.0,
        xg90_context_reliability=np.nan,
        xa90_context_reliability=np.nan,
        xg90_low_sample_adjusted=False,
    )
    payload = audit_statistical_truth(players, _projections(), expected_players=1)

    assert payload["ready"] is True
    assert payload["historical_sample_classes"] == {"zero_prior_minutes": 1}
    assert payload["preseason_sample_classes"] == {"no_preseason_sample": 1}
    assert any("prior-league minutes" in row for row in payload["warnings"])
    assert any("no measured preseason" in row for row in payload["warnings"])


def test_expired_material_availability_blocks_at_bundle_time() -> None:
    players = _players(
        availability_multiplier=0.2,
        availability_expires_at="2026-08-18T12:00:00Z",
    )
    payload = audit_statistical_truth(
        players,
        _projections(),
        expected_players=1,
        as_of="2026-08-19T09:00:00Z",
    )

    assert payload["ready"] is False
    assert payload["availability_evidence_states"] == {"expired": 1}
    assert any("availability evidence expired" in row for row in payload["blockers"])
