from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.decision import (
    CandidatePlayer,
    CandidateUniverse,
    CandidateUniverseScope,
    DecisionAction,
    DecisionChip,
    DecisionMechanics,
    RationalValue,
    TransferMove,
)
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import GlobalWorldId, ManagerStateId
from apex_fpl.core.manager_state import OwnedPlayer, calculate_selling_price_tenths
from apex_fpl.core.planning import PlanningChipUse, PlanningState
from apex_fpl.decision.planning_state import apply_planning_action


POSITIONS = {
    1: "GK",
    2: "GK",
    3: "DEF",
    4: "DEF",
    5: "DEF",
    6: "DEF",
    7: "DEF",
    8: "MID",
    9: "MID",
    10: "MID",
    11: "MID",
    12: "MID",
    13: "FWD",
    14: "FWD",
    15: "FWD",
    16: "DEF",
    17: "DEF",
}


def _ruleset():
    return load_ruleset(Path("config/rules/2026-2027.yaml"))


def _universe() -> CandidateUniverse:
    return CandidateUniverse(
        global_world_id=GlobalWorldId("planning-world"),
        scope=CandidateUniverseScope.FULL_OFFICIAL,
        players=tuple(
            CandidatePlayer(
                player_id=OfficialPlayerId(player_id),
                team_id=player_id,
                position=position,
                current_price_tenths=(55 if player_id == 16 else 45 if player_id == 17 else 50),
            )
            for player_id, position in POSITIONS.items()
        ),
        official_player_count=len(POSITIONS),
        source_artifact_ids=("sha256:" + "a" * 64,),
    )


def _state(*, gameweek: int = 2, free_transfers: int = 1) -> PlanningState:
    ruleset = _ruleset()
    universe = _universe()
    candidates = {row.player_id: row for row in universe.players}
    squad = []
    for player_id in range(1, 16):
        candidate = candidates[OfficialPlayerId(player_id)]
        basis = 45 if player_id == 3 else candidate.current_price_tenths
        squad.append(
            OwnedPlayer(
                player_id=candidate.player_id,
                team_id=candidate.team_id,
                position=candidate.position,
                purchase_basis_tenths=basis,
                current_price_tenths=candidate.current_price_tenths,
                selling_price_tenths=calculate_selling_price_tenths(
                    basis,
                    candidate.current_price_tenths,
                    ruleset=ruleset,
                ),
            )
        )
    return PlanningState(
        origin_manager_state_id=ManagerStateId("current-manager"),
        price_world_id=universe.global_world_id,
        season=ruleset.season,
        entry_id=63984,
        gameweek=gameweek,
        ruleset_id=ruleset.ruleset_id,
        bank_tenths=10,
        free_transfers=free_transfers,
        squad=tuple(squad),
        chips_used=(),
    )


def _mechanics(*, hit: int) -> DecisionMechanics:
    before = RationalValue(20, 1)
    return DecisionMechanics(
        xi_points=RationalValue(18, 1),
        autosub_points=RationalValue.zero(),
        captain_bonus=RationalValue(2, 1),
        squad_points_if_bench_boost=RationalValue.zero(),
        points_before_hits=before,
        hit_points=hit,
        objective_points=RationalValue(20 - hit, 1),
    )


def _action(
    state: PlanningState,
    *,
    chip: DecisionChip = DecisionChip.NONE,
    replacements: tuple[tuple[int, int], ...] = (),
    hit: int = 0,
) -> DecisionAction:
    squad = set(state.player_ids)
    transfers = []
    for outgoing, incoming in replacements:
        squad.remove(OfficialPlayerId(outgoing))
        squad.add(OfficialPlayerId(incoming))
        transfers.append(TransferMove(OfficialPlayerId(outgoing), OfficialPlayerId(incoming)))
    sale = sum(state.player(OfficialPlayerId(outgoing)).selling_price_tenths for outgoing, _ in replacements)
    candidates = {row.player_id: row for row in _universe().players}
    cost = sum(candidates[OfficialPlayerId(incoming)].current_price_tenths for _, incoming in replacements)
    temporary_bank = state.bank_tenths + sale - cost
    bank_after = state.bank_tenths if chip is DecisionChip.FREE_HIT else temporary_bank
    squad_ids = tuple(sorted(squad))
    xi_ids = tuple(
        player_id
        for player_id in (
            OfficialPlayerId(1),
            OfficialPlayerId(3),
            OfficialPlayerId(4),
            OfficialPlayerId(5),
            OfficialPlayerId(8),
            OfficialPlayerId(9),
            OfficialPlayerId(10),
            OfficialPlayerId(11),
            OfficialPlayerId(12),
            OfficialPlayerId(13),
            OfficialPlayerId(14),
        )
        if player_id in squad
    )
    # Replacements in these tests are defenders; preserve a legal 11 by using the new DEF.
    while len(xi_ids) < 11:
        for incoming in (OfficialPlayerId(16), OfficialPlayerId(17)):
            if incoming in squad and incoming not in xi_ids:
                xi_ids = (*xi_ids, incoming)
                if len(xi_ids) == 11:
                    break
    bench = set(squad_ids) - set(xi_ids)
    bench_gk = OfficialPlayerId(2)
    outfield = tuple(sorted(bench - {bench_gk}))
    return DecisionAction(
        chip=chip,
        transfers=tuple(transfers),
        squad_ids=squad_ids,
        xi_ids=xi_ids,
        captain_id=OfficialPlayerId(13),
        vice_captain_id=OfficialPlayerId(14),
        bench_gk_id=bench_gk,
        outfield_bench_order=outfield,
        bank_after_tenths=bank_after,
        mechanics=_mechanics(hit=hit),
    )


def test_normal_transfer_uses_exact_sale_basis_and_rolls_one_ft() -> None:
    state = _state(free_transfers=1)
    # Player 3 was bought at 4.5 and is 5.0; exact sale is below market price.
    assert state.player(OfficialPlayerId(3)).selling_price_tenths < 50
    action = _action(state, replacements=((3, 17),), hit=0)
    next_state = apply_planning_action(state, action, _universe(), ruleset=_ruleset())
    assert next_state.gameweek == 3
    assert next_state.bank_tenths == action.bank_after_tenths
    assert next_state.free_transfers == 1
    incoming = next_state.player(OfficialPlayerId(17))
    assert incoming.purchase_basis_tenths == 45
    assert incoming.current_price_tenths == 45
    assert incoming.selling_price_tenths == 45
    assert next_state.parent_state_id == state.planning_state_id
    assert next_state.parent_action_id == action.action_id


def test_second_normal_transfer_after_one_ft_costs_exactly_four_points() -> None:
    state = _state(free_transfers=1)
    action = _action(state, replacements=((3, 16), (4, 17)), hit=4)
    next_state = apply_planning_action(state, action, _universe(), ruleset=_ruleset())
    assert next_state.free_transfers == 1
    assert action.mechanics.objective_points == RationalValue(16, 1)

    with pytest.raises(ValueError, match="hit cost does not reconcile"):
        apply_planning_action(
            state,
            replace(action, mechanics=_mechanics(hit=0)),
            _universe(),
            ruleset=_ruleset(),
        )


def test_hold_banks_free_transfer_up_to_ruleset_cap() -> None:
    state = _state(free_transfers=3)
    next_state = apply_planning_action(
        state,
        _action(state),
        _universe(),
        ruleset=_ruleset(),
    )
    assert next_state.free_transfers == 4

    capped = _state(free_transfers=5)
    capped_next = apply_planning_action(
        capped,
        _action(capped),
        _universe(),
        ruleset=_ruleset(),
    )
    assert capped_next.free_transfers == 5


def test_wildcard_is_permanent_and_preserves_banked_transfers() -> None:
    state = _state(free_transfers=3)
    action = _action(
        state,
        chip=DecisionChip.WILDCARD,
        replacements=((3, 16), (4, 17)),
        hit=0,
    )
    next_state = apply_planning_action(state, action, _universe(), ruleset=_ruleset())
    assert OfficialPlayerId(16) in next_state.player_ids
    assert OfficialPlayerId(17) in next_state.player_ids
    assert next_state.free_transfers == 3
    assert any(
        row.chip == "WILDCARD" and row.gameweek == 2 and row.set_number == 1
        for row in next_state.chips_used
    )


def test_free_hit_reverts_permanent_squad_and_bank_and_preserves_ft() -> None:
    state = _state(free_transfers=3)
    action = _action(
        state,
        chip=DecisionChip.FREE_HIT,
        replacements=((3, 16), (4, 17)),
        hit=0,
    )
    next_state = apply_planning_action(state, action, _universe(), ruleset=_ruleset())
    assert next_state.squad == state.squad
    assert next_state.bank_tenths == state.bank_tenths
    assert next_state.free_transfers == state.free_transfers
    assert any(
        row.chip == "FREE_HIT" and row.gameweek == 2 and row.set_number == 1
        for row in next_state.chips_used
    )


def test_free_hit_cross_half_boundary_is_fail_closed() -> None:
    state = replace(
        _state(gameweek=20),
        chips_used=(PlanningChipUse(19, "FREE_HIT", 1),),
    )
    action = _action(state, chip=DecisionChip.FREE_HIT)
    with pytest.raises(ValueError, match="both configured boundary gameweeks"):
        apply_planning_action(state, action, _universe(), ruleset=_ruleset())


def test_atomic_bank_reconciliation_rejects_market_price_laundering() -> None:
    state = _state(free_transfers=1)
    action = _action(state, replacements=((3, 16),), hit=0)
    # Pretend the outgoing player can be sold at market price rather than exact selling value.
    forged = replace(action, bank_after_tenths=action.bank_after_tenths + 3)
    with pytest.raises(ValueError, match="simultaneous transfer finance"):
        apply_planning_action(state, forged, _universe(), ruleset=_ruleset())


def test_stale_planning_selling_value_is_rejected_before_action() -> None:
    state = _state()
    stale = replace(state.player(OfficialPlayerId(3)), selling_price_tenths=50)
    squad = tuple(stale if row.player_id == stale.player_id else row for row in state.squad)
    with pytest.raises(ValueError, match="selling value is stale"):
        apply_planning_action(
            replace(state, squad=squad),
            _action(state),
            _universe(),
            ruleset=_ruleset(),
        )
