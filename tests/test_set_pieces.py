from __future__ import annotations

import pandas as pd
import pytest

from apex_fpl.data.tactical import load_tactical_roles
from apex_fpl.models.projection import project_players
from apex_fpl.services.player_identity import activate_official_identity_registry


def test_verified_set_piece_shares_override_order_prior(tmp_path):
    activate_official_identity_registry(
        pd.DataFrame(
            [
                {
                    "player_id": 1,
                    "web_name": "Test",
                    "team": 1,
                    "team_name": "Example FC",
                    "position": "MID",
                }
            ]
        )
    )
    context = tmp_path / "tactical_roles.csv"
    pd.DataFrame(
        [
            {
                "player_id": 1,
                "source_player_name": "Test",
                "tactical_role": "penalty taker",
                "role_multiplier": 1.0,
                "role_confidence": 0.95,
                "penalty_share": 0.8,
                "corners_share": 0.5,
                "direct_freekick_share": 0.6,
                "indirect_freekick_share": 0.4,
                "lineup_evidence_type": "official_set_piece_confirmation",
                "source_name": "Example FC",
                "source_tier": "official_club",
                "source_url": "https://example.test/set-pieces",
                "published_at": "2026-08-07T07:00:00Z",
                "expires_at": "2026-08-14T07:00:00Z",
            }
        ]
    ).to_csv(context, index=False)
    loaded = load_tactical_roles(
        context, now=pd.Timestamp("2026-08-08T07:00:00Z").to_pydatetime()
    ).iloc[0]
    assert loaded["penalty_share"] == pytest.approx(0.8)
    assert loaded["direct_freekick_share"] == pytest.approx(0.6)


def test_stale_or_unverifiable_tactical_override_is_rejected(tmp_path):
    context = tmp_path / "tactical_roles.csv"
    pd.DataFrame(
        [
            {
                "player_id": 1,
                "source_player_name": "Test",
                "expected_minutes_override": 80,
                "lineup_evidence_type": "projected_xi",
                "source_name": "Unknown",
                "source_tier": "trusted_media",
                "source_url": "https://example.test/old",
                "published_at": "2026-08-01T07:00:00Z",
                "expires_at": "2026-08-02T07:00:00Z",
            }
        ]
    ).to_csv(context, index=False)
    with pytest.raises(ValueError, match="expired"):
        load_tactical_roles(
            context, now=pd.Timestamp("2026-08-08T07:00:00Z").to_pydatetime()
        )


def test_projection_carries_auditable_component_breakdown():
    players = pd.DataFrame(
        [
            {
                "player_id": 1,
                "team": 1,
                "position": "MID",
                "expected_minutes": 82,
                "appearance_probability": 0.96,
                "minutes_60_plus_probability": 0.88,
                "expected_goals_per_90": 0.35,
                "expected_assists_per_90": 0.22,
                "role_multiplier": 1.05,
                "penalties_order": 2,
                "corners_and_indirect_freekicks_order": 1,
                "direct_freekicks_order": 2,
                "penalty_share": 0.85,
                "corners_share": 0.70,
                "direct_freekick_share": 0.55,
                "indirect_freekick_share": 0.65,
                "bps": 120,
                "minutes": 900,
                "defensive_contribution_per_90": 8,
            }
        ]
    )
    fixtures = pd.DataFrame(
        [
            {
                "team": 1,
                "gw": 1,
                "opponent": 2,
                "is_home": True,
                "attack_multiplier": 1.1,
                "defence_multiplier": 1.0,
                "clean_sheet_prob": 0.35,
            }
        ]
    )
    row = project_players(players, fixtures, [1]).iloc[0]
    components = [
        "xp_appearance",
        "xp_attack",
        "xp_clean_sheet",
        "xp_defensive_contribution",
        "xp_saves",
        "xp_bonus_prior",
        "xp_set_piece_prior",
    ]
    assert row["apex_xp"] == pytest.approx(sum(float(row[c]) for c in components))
    assert row["penalty_share"] == pytest.approx(0.85)
    assert row["corners_share"] == pytest.approx(0.70)
    assert row["xp_set_piece_prior"] > 0
