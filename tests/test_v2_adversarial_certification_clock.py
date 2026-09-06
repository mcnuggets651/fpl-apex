from __future__ import annotations

from datetime import datetime, timezone

from apex.domain.models import (
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProviderHealth,
    ProviderRole,
    ProviderStatus,
    Qualification,
    SystemDecision,
)
from apex.governance.certification import certify


def _legal_inputs():
    specs = (
        (Position.GK, (1, 2)),
        (Position.DEF, (1, 2, 3, 4, 5)),
        (Position.MID, (3, 4, 5, 6, 7)),
        (Position.FWD, (6, 7, 8)),
    )
    players = []
    player_id = 1
    for position, teams in specs:
        for team_id in teams:
            players.append(
                OfficialPlayer(player_id, f"P{player_id}", team_id, position, 50, "a", True)
            )
            player_id += 1
    official = OfficialSnapshot(
        1,
        "2026-2027",
        "2026-09-03T06:00:00Z",
        "official",
        tuple(players),
        (),
        {3: "2026-09-12T10:00:00Z"},
    )
    squad = tuple(range(1, 16))
    xi = (1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15)
    bench = (2, 6, 7, 12)
    decision = SystemDecision(
        1,
        squad,
        xi,
        13,
        14,
        bench,
        decision_mode="INITIAL_SQUAD",
    )
    serving = ProviderStatus(
        "airsenal",
        ProviderRole.CHAMPION,
        0,
        ProviderHealth.HEALTHY,
        {1: Qualification.QUALIFIED},
        None,
        (),
        True,
    )
    return official, decision, serving


def test_malformed_valid_until_fails_closed_instead_of_crashing():
    official, decision, serving = _legal_inputs()
    result = certify(
        official=official,
        serving=serving,
        decision=decision,
        valid_until="definitely-not-an-iso-deadline",
        now=datetime(2026, 9, 3, 7, 0, tzinfo=timezone.utc),
    )
    assert result.actionable is False
    assert result.state.value == "BLOCKED"
    assert "SNAPSHOT_INCOHERENT" in {reason.value for reason in result.reasons}
    assert any("valid_until" in warning for warning in result.warnings)
