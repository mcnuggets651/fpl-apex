"""Exact hypothetical FPL transitions for the receding-horizon planner.

These functions intentionally operate on :class:`PlanningState`, never by mutating or
relabeling a future state as ``ManagerState.CURRENT_EXACT``. Transfer finance is atomic:
all outgoing realised selling resources and all incoming Official-current costs reconcile
as one FPL action, avoiding artificial intermediate-budget or club-limit constraints.
"""

from __future__ import annotations

from apex_fpl.core.decision import (
    CandidatePlayer,
    CandidateUniverse,
    DecisionAction,
    DecisionChip,
)
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.manager_state import (
    ManagerState,
    OwnedPlayer,
    calculate_selling_price_tenths,
)
from apex_fpl.core.planning import PlanningChipUse, PlanningState
from apex_fpl.core.rules import RuleSet


def _chip_set(gameweek: int, *, ruleset: RuleSet) -> int:
    first_last = ruleset.integer("FPL-CHIP-FIRST-SET-LAST-GW-001")
    second_first = ruleset.integer("FPL-CHIP-SECOND-SET-FIRST-GW-001")
    if gameweek <= first_last:
        return 1
    if gameweek >= second_first:
        return 2
    raise ValueError(f"gameweek {gameweek} is outside configured chip sets")


def _chip_ledger_name(chip: DecisionChip) -> str:
    mapping = {
        DecisionChip.WILDCARD: "WILDCARD",
        DecisionChip.FREE_HIT: "FREE_HIT",
        DecisionChip.TRIPLE_CAPTAIN: "TRIPLE_CAPTAIN",
        DecisionChip.BENCH_BOOST: "BENCH_BOOST",
    }
    if chip is DecisionChip.NONE:
        raise ValueError("NONE has no chip-ledger identity")
    return mapping[chip]


def _validate_chip_available(
    state: PlanningState,
    chip: DecisionChip,
    *,
    ruleset: RuleSet,
) -> None:
    if chip is DecisionChip.NONE:
        return
    set_number = _chip_set(state.gameweek, ruleset=ruleset)
    ledger_name = _chip_ledger_name(chip)
    if any(
        row.chip == ledger_name and row.set_number == set_number
        for row in state.chips_used
    ):
        raise ValueError(f"planning chip {ledger_name} already used in set {set_number}")
    if chip is DecisionChip.FREE_HIT:
        if state.gameweek in set(ruleset.value("FPL-FREE-HIT-DISALLOWED-GWS-001")):
            raise ValueError(f"Free Hit is disallowed in GW{state.gameweek}")
        boundary = ruleset.mapping("FPL-FREE-HIT-CROSS-HALF-CONSECUTIVE-001")
        if (
            boundary.get("allowed") is False
            and state.gameweek == int(boundary["second_half_gw"])
            and any(
                row.chip == "FREE_HIT"
                and row.gameweek == int(boundary["first_half_gw"])
                for row in state.chips_used
            )
        ):
            raise ValueError("Free Hit cannot be used in both configured boundary gameweeks")
    if chip is DecisionChip.WILDCARD and state.gameweek in set(
        ruleset.value("FPL-WILDCARD-DISALLOWED-GWS-001")
    ):
        raise ValueError(f"Wildcard is disallowed in GW{state.gameweek}")


def _validate_state_surface(
    state: PlanningState,
    universe: CandidateUniverse,
    *,
    ruleset: RuleSet,
) -> dict[OfficialPlayerId, CandidatePlayer]:
    if state.season != ruleset.season:
        raise ValueError("PlanningState season does not match RuleSet")
    if state.ruleset_id != ruleset.ruleset_id:
        raise ValueError("PlanningState RuleSet identity mismatch")
    if state.price_world_id != universe.global_world_id:
        raise ValueError("PlanningState price world does not match candidate universe")
    candidates = {row.player_id: row for row in universe.players}
    for owned in state.squad:
        candidate = candidates.get(owned.player_id)
        if candidate is None:
            raise ValueError(f"owned planning player {owned.player_id} is outside universe")
        if (
            candidate.team_id != owned.team_id
            or candidate.position != owned.position
            or candidate.current_price_tenths != owned.current_price_tenths
        ):
            raise ValueError(f"owned planning player {owned.player_id} facts mismatch universe")
        expected_sale = calculate_selling_price_tenths(
            owned.purchase_basis_tenths,
            owned.current_price_tenths,
            ruleset=ruleset,
        )
        if owned.selling_price_tenths != expected_sale:
            raise ValueError(f"owned planning player {owned.player_id} selling value is stale")
    return candidates


def planning_state_from_manager_state(
    state: ManagerState,
    universe: CandidateUniverse,
    *,
    ruleset: RuleSet,
) -> PlanningState:
    """Seal one hypothetical planning root from current exact manager truth."""

    state.require_decision_safe(ruleset=ruleset)
    provisional = PlanningState(
        origin_manager_state_id=state.manager_state_id,
        price_world_id=universe.global_world_id,
        season=state.season,
        entry_id=state.entry_id,
        gameweek=state.gameweek,
        ruleset_id=state.ruleset_id,
        bank_tenths=state.bank_tenths,
        free_transfers=state.free_transfers,
        squad=state.squad,
        chips_used=tuple(
            PlanningChipUse(row.gameweek, row.chip, row.set_number)
            for row in state.chips_used
        ),
    )
    _validate_state_surface(provisional, universe, ruleset=ruleset)
    return provisional


def _validate_action_transfer_identity(
    state: PlanningState,
    action: DecisionAction,
    candidates: dict[OfficialPlayerId, CandidatePlayer],
) -> tuple[set[OfficialPlayerId], set[OfficialPlayerId]]:
    current_ids = set(state.player_ids)
    result_ids = set(action.squad_ids)
    outgoing_ids = current_ids - result_ids
    incoming_ids = result_ids - current_ids
    declared_out = {row.outgoing_player_id for row in action.transfers}
    declared_in = {row.incoming_player_id for row in action.transfers}
    if not (
        outgoing_ids == declared_out
        and incoming_ids == declared_in
        and len(action.transfers) == len(outgoing_ids) == len(incoming_ids)
    ):
        raise ValueError("planning transfer set does not reconcile squad delta")
    for move in action.transfers:
        outgoing = state.player(move.outgoing_player_id)
        incoming = candidates.get(move.incoming_player_id)
        if incoming is None:
            raise ValueError(
                f"planning incoming player {move.incoming_player_id} is outside universe"
            )
        if outgoing.position != incoming.position:
            raise ValueError("planning transfer must preserve exact FPL position")
    return outgoing_ids, incoming_ids


def _legal_action_squad(
    action: DecisionAction,
    candidates: dict[OfficialPlayerId, CandidatePlayer],
    *,
    ruleset: RuleSet,
) -> tuple[CandidatePlayer, ...]:
    try:
        squad = tuple(candidates[player_id] for player_id in action.squad_ids)
    except KeyError as exc:
        raise ValueError("planning action squad contains player outside universe") from exc
    errors = ruleset.validate_squad(
        positions=(row.position for row in squad),
        club_ids=(row.team_id for row in squad),
        prices_tenths=(row.current_price_tenths for row in squad),
        enforce_budget=False,
    )
    if errors:
        raise ValueError("planning action squad is not RuleSet-legal: " + "; ".join(errors))
    return squad


def _expected_hit_points(
    state: PlanningState,
    action: DecisionAction,
    *,
    ruleset: RuleSet,
) -> int:
    if action.chip in {DecisionChip.WILDCARD, DecisionChip.FREE_HIT}:
        return 0
    extra = max(0, len(action.transfers) - state.free_transfers)
    return extra * ruleset.integer("FPL-EXTRA-TRANSFER-HIT-POINTS-001")


def _next_free_transfers(
    state: PlanningState,
    action: DecisionAction,
    *,
    ruleset: RuleSet,
) -> int:
    if action.chip is DecisionChip.WILDCARD and ruleset.value(
        "FPL-WILDCARD-PRESERVES-BANKED-TRANSFERS-001"
    ) is True:
        return state.free_transfers
    if action.chip is DecisionChip.FREE_HIT and ruleset.value(
        "FPL-FREE-HIT-PRESERVES-BANKED-TRANSFERS-001"
    ) is True:
        return state.free_transfers
    after_action = max(0, state.free_transfers - len(action.transfers))
    return min(
        ruleset.integer("FPL-FREE-TRANSFER-BANK-MAX-001"),
        after_action + ruleset.integer("FPL-FREE-TRANSFER-GRANT-001"),
    )


def _permanent_squad_after_action(
    state: PlanningState,
    action: DecisionAction,
    candidates: dict[OfficialPlayerId, CandidatePlayer],
    *,
    ruleset: RuleSet,
) -> tuple[OwnedPlayer, ...]:
    if action.chip is DecisionChip.FREE_HIT:
        return state.squad
    current = {row.player_id: row for row in state.squad}
    rows: list[OwnedPlayer] = []
    for player_id in action.squad_ids:
        retained = current.get(player_id)
        if retained is not None:
            rows.append(retained)
            continue
        candidate = candidates[player_id]
        rows.append(
            OwnedPlayer(
                player_id=candidate.player_id,
                team_id=candidate.team_id,
                position=candidate.position,
                purchase_basis_tenths=candidate.current_price_tenths,
                current_price_tenths=candidate.current_price_tenths,
                selling_price_tenths=candidate.current_price_tenths,
            )
        )
    permanent = tuple(sorted(rows, key=lambda row: int(row.player_id)))
    return tuple(
        OwnedPlayer(
            player_id=row.player_id,
            team_id=row.team_id,
            position=row.position,
            purchase_basis_tenths=row.purchase_basis_tenths,
            current_price_tenths=row.current_price_tenths,
            selling_price_tenths=calculate_selling_price_tenths(
                row.purchase_basis_tenths,
                row.current_price_tenths,
                ruleset=ruleset,
            ),
        )
        for row in permanent
    )


def apply_planning_action(
    state: PlanningState,
    action: DecisionAction,
    universe: CandidateUniverse,
    *,
    ruleset: RuleSet,
) -> PlanningState:
    """Apply one exact current action and return the next hypothetical deadline state."""

    candidates = _validate_state_surface(state, universe, ruleset=ruleset)
    _validate_chip_available(state, action.chip, ruleset=ruleset)
    _legal_action_squad(action, candidates, ruleset=ruleset)
    outgoing_ids, incoming_ids = _validate_action_transfer_identity(state, action, candidates)

    sale_value = sum(
        state.player(player_id).selling_price_tenths for player_id in outgoing_ids
    )
    incoming_cost = sum(
        candidates[player_id].current_price_tenths for player_id in incoming_ids
    )
    temporary_bank = state.bank_tenths + sale_value - incoming_cost
    if temporary_bank < 0:
        raise ValueError("planning action is unaffordable under exact selling resources")
    expected_bank = (
        state.bank_tenths if action.chip is DecisionChip.FREE_HIT else temporary_bank
    )
    if action.bank_after_tenths != expected_bank:
        raise ValueError(
            "planning action bank does not reconcile exact simultaneous transfer finance"
        )

    expected_hit = _expected_hit_points(state, action, ruleset=ruleset)
    if action.mechanics.hit_points != expected_hit:
        raise ValueError("planning action hit cost does not reconcile exact FPL transfer rules")

    chips = state.chips_used
    if action.chip is not DecisionChip.NONE:
        chips = tuple(
            sorted(
                (
                    *chips,
                    PlanningChipUse(
                        state.gameweek,
                        _chip_ledger_name(action.chip),
                        _chip_set(state.gameweek, ruleset=ruleset),
                    ),
                )
            )
        )

    next_squad = _permanent_squad_after_action(
        state,
        action,
        candidates,
        ruleset=ruleset,
    )
    next_bank = (
        state.bank_tenths if action.chip is DecisionChip.FREE_HIT else expected_bank
    )
    next_state = PlanningState(
        origin_manager_state_id=state.origin_manager_state_id,
        price_world_id=state.price_world_id,
        season=state.season,
        entry_id=state.entry_id,
        gameweek=state.gameweek + 1,
        ruleset_id=state.ruleset_id,
        bank_tenths=next_bank,
        free_transfers=_next_free_transfers(state, action, ruleset=ruleset),
        squad=next_squad,
        chips_used=chips,
        parent_state_id=state.planning_state_id,
        parent_action_id=action.action_id,
    )
    _validate_state_surface(next_state, universe, ruleset=ruleset)
    return next_state
