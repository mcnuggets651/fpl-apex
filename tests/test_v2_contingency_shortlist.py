from __future__ import annotations

from apex.decision.optimiser import optimise_initial_squad
from apex.decision.transfers import optimise_transfer_horizon
from apex.domain.models import (
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProductionProjectionSurface,
    ProjectionRow,
    TeamState,
)


def _initial_shortlist_fixture():
    players = []
    specs = (
        (Position.GK, [5.0, 1.0]),
        # Five of these six defenders must be selected. The primary xP solution
        # takes A=10.0 over B=9.7, but B's 50% appearance makes vice fallback
        # materially valuable under the exact contingency evaluator.
        (Position.DEF, [10.4, 10.3, 10.2, 10.1, 10.0, 9.7]),
        (Position.MID, [5.0, 4.9, 4.8, 4.7, 1.0]),
        (Position.FWD, [4.6, 4.5, 1.0]),
    )
    xp = {}
    player_id = 1
    for position, values in specs:
        for value in values:
            players.append(
                OfficialPlayer(
                    player_id,
                    f"P{player_id}",
                    player_id,
                    position,
                    45,
                    "a",
                    True,
                )
            )
            xp[player_id] = value
            player_id += 1

    official = OfficialSnapshot(
        1,
        "2026-2027",
        "2026-08-29T12:00:00Z",
        "official",
        tuple(players),
        (),
        {3: "2026-09-05T10:00:00Z"},
    )
    appearance = {player.element_id: 1.0 for player in players}
    # DEF ids are 3..8; id 8 is B.
    appearance[8] = 0.5
    surface = ProductionProjectionSurface(
        1,
        "airsenal",
        "pinned",
        "2026-08-29T12:00:00Z",
        official.season,
        official.source_hash,
        "fpl-2026-27-v1",
        (1,),
        tuple(
            ProjectionRow(
                player.element_id,
                3,
                1,
                xp[player.element_id],
                p_appearance=appearance[player.element_id],
            )
            for player in players
        ),
    )
    return official, surface


def test_initial_shortlist_can_select_exact_contingency_challenger() -> None:
    official, surface = _initial_shortlist_fixture()
    result = optimise_initial_squad(
        official,
        surface,
        candidate_limit=8,
        candidate_regret_fraction=0.05,
    )

    assert result.status == "OPTIMAL"
    assert result.decision is not None
    assert result.raw_solver["shortlist_complete"] is True
    assert (
        result.raw_solver["selection_policy"]
        == "EXACT_CONTINGENCY_CERTIFIED_SHORTLIST"
    )
    assert result.raw_solver["selected_generation_rank"] > 1
    assert 8 in result.decision.squad_ids
    assert 7 not in result.decision.squad_ids


def _transfer_fixture():
    players = []
    player_id = 1
    specs = [
        (Position.GK, (1, 2)),
        (Position.DEF, (1, 2, 3, 4, 5)),
        (Position.MID, (3, 4, 5, 6, 7)),
        (Position.FWD, (6, 7, 8)),
    ]
    for position, team_ids in specs:
        for team_id in team_ids:
            players.append(
                OfficialPlayer(
                    player_id,
                    f"P{player_id}",
                    team_id,
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
                    9 + index,
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
        "2026-08-29T12:00:00Z",
        "official",
        tuple(players),
        (),
        {
            3: "2026-09-05T10:00:00Z",
            4: "2026-09-12T10:00:00Z",
        },
    )
    squad = tuple(range(1, 16))
    team = TeamState(
        1,
        1,
        2,
        squad,
        0,
        1,
        {player_id: 50 for player_id in squad},
        {player_id: 50 for player_id in squad},
        None,
        True,
    )
    rows = []
    for player in players:
        points = 10.0 if player.element_id > 15 else 3.0
        rows.extend(
            (
                ProjectionRow(
                    player.element_id,
                    3,
                    1,
                    points,
                    p_appearance=1.0,
                ),
                ProjectionRow(
                    player.element_id,
                    4,
                    2,
                    points,
                    p_appearance=1.0,
                ),
            )
        )
    surface = ProductionProjectionSurface(
        1,
        "airsenal",
        "pinned",
        "2026-08-29T12:00:00Z",
        official.season,
        official.source_hash,
        "fpl-2026-27-v1",
        (1, 2),
        tuple(rows),
    )
    return official, team, surface


def test_transfer_shortlist_falls_back_when_candidate_cap_prevents_proof(
    monkeypatch,
) -> None:
    official, team, surface = _transfer_fixture()
    from apex.decision import transfers

    real_milp = transfers.milp
    calls = []

    def counted_milp(*args, **kwargs):
        calls.append(1)
        return real_milp(*args, **kwargs)

    monkeypatch.setattr(transfers, "milp", counted_milp)
    result = optimise_transfer_horizon(
        official,
        surface,
        team,
        max_horizon=2,
        candidate_limit=1,
        candidate_regret_fraction=0.05,
    )

    assert result.status == "OPTIMAL"
    assert result.decision is not None
    assert result.solver["shortlist_complete"] is False
    assert (
        result.solver["selection_policy"]
        == "PRIMARY_MAX_EV_FALLBACK_UNCERTIFIED_SHORTLIST"
    )
    assert result.solver["selected_generation_rank"] == 1
    assert "candidate limit" in result.solver["reason"]
    assert len(calls) == 1
    assert result.decision.horizon == 2
