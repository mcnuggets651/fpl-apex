from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from apex_fpl.data.tactical import load_tactical_roles
from apex_fpl.services.player_identity import activate_official_identity_registry


def _official() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": 1, "web_name": "Coyle", "team": 2, "team_name": "Hull", "position": "DEF"},
            {"player_id": 2, "web_name": "Gabriel", "team": 1, "team_name": "Arsenal", "position": "DEF"},
        ]
    )


def _material_row() -> dict:
    return {
        "player_id": 1,
        "source_player_name": "Coyle",
        "tactical_role": "right-back",
        "role_multiplier": 1.0,
        "role_confidence": 0.9,
        "expected_minutes_override": 82,
        "lineup_evidence_type": "official_manager_comment",
        "context_reason": "Expected starter",
        "source_name": "Example FC",
        "source_tier": "official_club",
        "source_url": "https://example.test/team-news",
        "published_at": "2026-08-18T12:00:00Z",
        "expires_at": "2026-08-23T12:00:00Z",
    }


def test_tracked_tactical_overrides_are_current_and_valid():
    """Fail fast when committed live tactical evidence has expired."""
    loaded = load_tactical_roles(Path("data/manual/tactical_roles.csv"))
    assert loaded["player_id"].is_unique


def test_tactical_valid_id_wrong_name_fails_before_attachment(tmp_path):
    activate_official_identity_registry(_official())
    path = tmp_path / "tactical.csv"
    row = _material_row()
    row["source_player_name"] = "Gabriel"
    pd.DataFrame([row]).to_csv(path, index=False)

    with pytest.raises(ValueError, match="identity integrity failed"):
        load_tactical_roles(
            path,
            now=datetime(2026, 8, 19, tzinfo=timezone.utc),
        )


def test_tactical_correct_identity_is_preserved(tmp_path):
    activate_official_identity_registry(_official())
    path = tmp_path / "tactical.csv"
    pd.DataFrame([_material_row()]).to_csv(path, index=False)

    loaded = load_tactical_roles(
        path,
        now=datetime(2026, 8, 19, tzinfo=timezone.utc),
    )

    assert loaded.iloc[0]["player_id"] == 1
    assert loaded.iloc[0]["source_player_name"] == "Coyle"
    assert loaded.iloc[0]["expected_minutes_override"] == pytest.approx(82.0)
