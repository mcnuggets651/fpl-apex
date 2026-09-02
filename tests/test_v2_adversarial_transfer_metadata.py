from __future__ import annotations

from apex.decision.validate import validate_system_decision
from apex.domain.models import OfficialPlayer, OfficialSnapshot, Position, SystemDecision, TeamState


def _official_and_team():
    players = []
    pid = 1
    for team in range(1, 8):
        for position, count in (
            (Position.GK, 1),
            (Position.DEF, 2),
            (Position.MID, 2),
            (Position.FWD, 1),
        ):
            for _ in range(count):
                players.append(OfficialPlayer(pid, f"P{pid}", team, position, 45, "a", True))
                pid += 1
    official = OfficialSnapshot(
        1,
        "2026-2027",
        "2026-09-02T10:00:00Z",
        "official-hash",
        tuple(players),
        (),
        {3: "2026-09-12T10:00:00Z"},
    )

    # Build a legal 15-man squad: 2 GK, 5 DEF, 5 MID, 3 FWD, max three per team.
    by_position = {position: [] for position in Position}
    for player in players:
        by_position[player.position].append(player.element_id)
    squad = tuple(
        by_position[Position.GK][:2]
        + by_position[Position.DEF][:5]
        + by_position[Position.MID][:5]
        + by_position[Position.FWD][:3]
    )
    team = TeamState(
        1,
        63984,
        2,
        squad,
        0,
        1,
        {player_id: 45 for player_id in squad},
        {player_id: 45 for player_id in squad},
        None,
        True,
    )
    return official, team


def test_duplicate_transfer_ids_are_rejected_before_certification():
    official, team = _official_and_team()
    players = official.player_map()
    outgoing = next(
        player_id for player_id in team.squad_ids if players[player_id].position == Position.MID
    )
    incoming = next(
        player.element_id
        for player in official.players
        if player.position == Position.MID and player.element_id not in team.squad_ids
    )
    resulting = tuple(
        incoming if player_id == outgoing else player_id for player_id in team.squad_ids
    )
    xi = resulting[:11]
    decision = SystemDecision(
        1,
        "TRANSFER_HORIZON",
        resulting,
        xi,
        xi[0],
        xi[1],
        resulting[11:],
        (incoming, incoming),
        (outgoing, outgoing),
        2,
        0,
        50.0,
    )

    errors = validate_system_decision(official, decision, team)
    assert any("duplicate" in error.lower() and "transfer" in error.lower() for error in errors)
