from dataclasses import replace

from apex.decision.transfers import optimise_transfer_horizon
from apex.domain.models import (
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProductionProjectionSurface,
    ProjectionRow,
    TeamState,
)


def setup():
    players = []
    player_id = 1
    specs = [
        (Position.GK, 2),
        (Position.DEF, 5),
        (Position.MID, 5),
        (Position.FWD, 3),
    ]
    for position, count in specs:
        for index in range(count):
            players.append(
                OfficialPlayer(
                    player_id,
                    f"P{player_id}",
                    1 + index % 5,
                    position,
                    50,
                    "a",
                    True,
                )
            )
            player_id += 1
    for position in Position:
        for index in range(4):
            players.append(
                OfficialPlayer(
                    player_id,
                    f"A{player_id}",
                    6 + index % 2,
                    position,
                    50,
                    "a",
                    True,
                )
            )
            player_id += 1
    official = OfficialSnapshot(
        1,
        "2026-2027",
        "2026-08-28T10:00:00Z",
        "s",
        tuple(players),
        (),
        {
            2: "2026-08-29T10:00:00Z",
            3: "2026-09-05T10:00:00Z",
        },
    )
    squad = tuple(range(1, 16))
    team = TeamState(
        1,
        1,
        1,
        squad,
        0,
        1,
        {player: 50 for player in squad},
        {player: 50 for player in squad},
        None,
        True,
    )
    rows = []
    for player in players:
        rows.append(
            ProjectionRow(
                player.element_id,
                2,
                1,
                10 if player.element_id > 15 else 3,
            )
        )
        rows.append(
            ProjectionRow(
                player.element_id,
                3,
                2,
                10 if player.element_id > 15 else 3,
            )
        )
    surface = ProductionProjectionSurface(
        1,
        "p",
        "v",
        "2026-08-28T10:00:00Z",
        official.season,
        official.source_hash,
        "2026-2027",
        (1, 2),
        tuple(rows),
    )
    return official, team, surface


def test_h1_only_withholds_discretionary_transfer():
    official, team, surface = setup()
    result = optimise_transfer_horizon(
        official,
        surface,
        team,
        max_horizon=1,
    )
    assert result.status == "WITHHELD_H1_ONLY"
    assert result.decision.transfers_in == ()


def test_h2_uses_transfer_when_multiweek_ev_beats_hit_and_cash():
    official, team, surface = setup()
    result = optimise_transfer_horizon(
        official,
        surface,
        team,
        max_horizon=2,
    )
    assert result.status == "OPTIMAL"
    assert result.decision is not None
    assert len(result.weeks) == 2
    assert len(result.decision.transfers_in) == len(
        result.decision.transfers_out
    )


def test_zero_remaining_free_transfers_charges_first_new_transfer_as_hit():
    official, team, _ = setup()
    team = replace(team, free_transfers=0)
    rows = []
    for player in official.players:
        points = 15.0 if player.element_id == 20 else 3.0
        rows.extend(
            (
                ProjectionRow(player.element_id, 2, 1, points),
                ProjectionRow(player.element_id, 3, 2, points),
            )
        )
    surface = ProductionProjectionSurface(
        1,
        "p",
        "v",
        "2026-08-28T10:00:00Z",
        official.season,
        official.source_hash,
        "2026-2027",
        (1, 2),
        tuple(rows),
    )

    result = optimise_transfer_horizon(
        official,
        surface,
        team,
        max_horizon=2,
    )

    assert result.status == "OPTIMAL"
    assert result.decision is not None
    assert result.decision.transfers_in == (20,)
    assert len(result.decision.transfers_out) == 1
    assert result.decision.transfer_hits == 1
    assert result.weeks[0].free_transfers == 0
    assert result.weeks[0].hits == 1
    assert result.weeks[1].free_transfers == 1
