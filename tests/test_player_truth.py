from __future__ import annotations

import pandas as pd
import pytest

from apex_fpl.models.projection import project_players
from apex_fpl.services.player_truth import audit_player_truth


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


def _player(**extra) -> dict:
    row = {
        "player_id": 1,
        "web_name": "Test",
        "team": 1,
        "team_name": "Example",
        "position": "MID",
        "price": 6.0,
        "status": "a",
        "expected_minutes": 75,
        "expected_goals_per_90": 0.30,
        "expected_assists_per_90": 0.20,
        "role_multiplier": 1.0,
        "tactical_role": "advanced midfielder",
        "tactical_role_source": "statistical_inference",
        "role_confidence": 0.65,
        "minutes_confidence": 0.70,
    }
    row.update(extra)
    return row


def _auditable_projection(players: pd.DataFrame) -> pd.DataFrame:
    projections = project_players(players, _fixture(), [1])
    projections["source_present_airsenal"] = True
    return projections


def test_ordinal_set_piece_order_never_becomes_literal_share():
    players = pd.DataFrame(
        [
            _player(
                penalties_order=2,
                corners_and_indirect_freekicks_order=1,
                direct_freekicks_order=3,
            )
        ]
    )
    row = project_players(players, _fixture(), [1]).iloc[0]

    assert row["penalty_share"] == pytest.approx(0.0)
    assert row["corners_share"] == pytest.approx(0.0)
    assert row["direct_freekick_share"] == pytest.approx(0.0)
    assert row["indirect_freekick_share"] == pytest.approx(0.0)
    assert row["xp_set_piece_prior"] == pytest.approx(0.0)


def test_explicit_share_override_still_remains_available_for_sourced_inputs():
    players = pd.DataFrame(
        [
            _player(
                penalties_order=2,
                penalty_share=0.80,
                source_tier="official_club",
                source_url="https://example.test/set-pieces",
                lineup_evidence_type="official_set_piece_confirmation",
            )
        ]
    )
    row = project_players(players, _fixture(), [1]).iloc[0]

    assert row["penalty_share"] == pytest.approx(0.80)
    assert row["xp_set_piece_prior"] > 0


def test_all_player_truth_requires_complete_facts_and_required_expert_pairs():
    players = pd.DataFrame([_player()])
    projections = _auditable_projection(players)
    payload = audit_player_truth(players, projections, expected_players=1)

    assert payload["ready"] is True
    assert payload["hard_fact_coverage"] == pytest.approx(1.0)
    assert payload["canonical_projection_pair_coverage"] == pytest.approx(1.0)
    assert payload["airsenal_projection_pair_coverage"] == pytest.approx(1.0)
    assert payload["players"][0]["minutes_class"].startswith("forecast_")
    assert payload["players"][0]["role_class"] == "statistical_inference"


def test_unreconciled_missing_airsenal_pair_is_a_truth_blocker():
    players = pd.DataFrame([_player()])
    projections = _auditable_projection(players)
    projections["source_present_airsenal"] = False
    payload = audit_player_truth(players, projections, expected_players=1)

    assert payload["ready"] is False
    assert payload["airsenal_projection_pair_coverage"] == pytest.approx(0.0)
    assert any(
        "AIrsenal source absence is not explicitly reconciled" in row
        for row in payload["blockers"]
    )


def test_unsourced_set_piece_share_is_a_truth_blocker():
    players = pd.DataFrame([_player(penalty_share=0.45, penalties_order=2)])
    projections = pd.DataFrame(
        [
            {
                "player_id": 1,
                "gw": 1,
                "xp_set_piece_prior": 0.13,
                "source_present_airsenal": True,
            }
        ]
    )
    payload = audit_player_truth(players, projections, expected_players=1)

    assert payload["ready"] is False
    assert any("without trusted current provenance" in row for row in payload["blockers"])
    assert any("set-piece xP exists" in row for row in payload["blockers"])
