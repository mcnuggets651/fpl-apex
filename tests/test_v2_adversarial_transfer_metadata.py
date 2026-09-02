from __future__ import annotations

from apex.decision.validate import validate_system_decision
from apex.domain.models import (
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    SystemDecision,
    TeamState,
)


def _official_and_team():
    players = []
    pid = 1
    by_team_position: dict[tuple[int, Position], list[int]] = {}
    for team in range(1, 8):
        for position, count in (
            (Position.GK, 1),
            (Position.DEF, 2),
            (Position.MID, 2),
            (Position.FWD, 1),
        ):
            by_team_position[team, position] = []
            for _ in range(count):
                players.append(
                    OfficialPlayer(pid, f"P{pid}", team, position, 45, "a", True)
                )
                by_team_position[team, position].append(pid)
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

    squad = tuple(
        [
            by_team_position[1, Position.GK][0],
            by_team_position[2, Position.GK][0],
        ]
        + by_team_position[3, Position.DEF]
        + by_team_position[4, Position.DEF]
        + [by_team_position[5, Position.DEF][0]]
        + by_team_position[5, Position.MID]
        + by_team_position[6, Position.MID]
        + [by_team_position[7, Position.MID][0]]
        + [
            by_team_position[1, Position.FWD][0],
            by_team_position[2, Position.FWD][0],
            by_team_position[7, Position.FWD][0],
        ]
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
    return official, team, by_team_position


def test_duplicate_transfer_ids_are_rejected_before_certification():
    official, team, by_team_position = _official_and_team()
    outgoing = by_team_position[6, Position.MID][0]
    incoming = by_team_position[3, Position.MID][0]
    resulting = tuple(
        incoming if player_id == outgoing else player_id for player_id in team.squad_ids
    )
    player_map = official.player_map()
    gks = [pid for pid in resulting if player_map[pid].position == Position.GK]
    defs = [pid for pid in resulting if player_map[pid].position == Position.DEF]
    mids = [pid for pid in resulting if player_map[pid].position == Position.MID]
    fwds = [pid for pid in resulting if player_map[pid].position == Position.FWD]
    xi = tuple([gks[0], *defs[:4], *mids[:4], *fwds[:2]])
    bench = tuple([gks[1], defs[4], mids[4], fwds[2]])
    decision = SystemDecision(
        schema_version=1,
        squad_ids=resulting,
        xi_ids=xi,
        captain_id=xi[0],
        vice_captain_id=xi[1],
        bench_order=bench,
        transfers_in=(incoming, incoming),
        transfers_out=(outgoing, outgoing),
        objective=50.0,
        horizon=2,
        transfer_hits=0,
        decision_mode="TRANSFER_HORIZON",
    )

    errors = validate_system_decision(official, decision, team)
    assert any(
        "duplicate" in error.lower() and "transfer" in error.lower()
        for error in errors
    )
