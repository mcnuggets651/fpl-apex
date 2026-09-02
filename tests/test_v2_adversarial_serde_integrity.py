from __future__ import annotations

import pytest

from apex.domain.models import (
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    TeamState,
    dataclass_to_dict,
)
from apex.runtime.serde import official_from_dict, team_from_dict


def _official() -> OfficialSnapshot:
    return OfficialSnapshot(
        1,
        "2026-2027",
        "2026-09-02T12:00:00Z",
        "a" * 64,
        (
            OfficialPlayer(
                element_id=1,
                web_name="One",
                team_id=1,
                position=Position.MID,
                price_tenths=50,
                status="a",
                can_transact=False,
                fpl_code=123456,
            ),
        ),
        (),
        {3: "2026-09-12T10:00:00Z"},
    )


def test_official_roundtrip_preserves_stable_player_identity():
    original = _official()
    restored = official_from_dict(dataclass_to_dict(original))
    assert restored == original
    assert restored.players[0].fpl_code == 123456


def test_official_deserializer_rejects_string_boolean():
    payload = dataclass_to_dict(_official())
    payload["players"][0]["can_transact"] = "false"
    with pytest.raises(ValueError, match="can_transact"):
        official_from_dict(payload)


def test_team_deserializer_rejects_string_transfer_completeness():
    team = TeamState(
        1,
        63984,
        2,
        tuple(range(1, 16)),
        5,
        2,
        state_complete_for_transfers=False,
    )
    payload = dataclass_to_dict(team)
    payload["state_complete_for_transfers"] = "false"
    with pytest.raises(ValueError, match="state_complete_for_transfers"):
        team_from_dict(payload)


def test_team_roundtrip_preserves_boolean_exactly():
    team = TeamState(
        1,
        63984,
        2,
        tuple(range(1, 16)),
        5,
        2,
        state_complete_for_transfers=False,
    )
    assert team_from_dict(dataclass_to_dict(team)) == team
