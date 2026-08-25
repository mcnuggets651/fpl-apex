"""Shared exact FPL action surface for tactical and receding-horizon engines.

There must be one implementation of transfer finance, chip availability, squad legality
and submission optimisation.  Tactical ``ManagerState`` and hypothetical ``PlanningState``
are different truth types, but both expose the same immutable FPL facts needed to enumerate
one deadline action.  This module consumes only that structural view and never promotes a
hypothetical planning state to current manager truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations, product
from typing import Protocol

from apex_fpl.core.decision import (
    CandidatePlayer,
    CandidateUniverse,
    DecisionAction,
    DecisionChip,
    RationalValue,
    TransferMove,
)
from apex_fpl.core.forecast import Forecast
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.manager_state import OwnedPlayer
from apex_fpl.core.rules import RuleSet

from .mechanics import PlayerGameweekValue, build_gameweek_values, optimise_squad_submission


class ChipUseView(Protocol):
    gameweek: int
    chip: str
    set_number: int


class DeadlineStateView(Protocol):
    gameweek: int
    bank_tenths: int
    free_transfers: int
    squad: tuple[OwnedPlayer, ...]
    chips_used: tuple[ChipUseView, ...]


@dataclass(frozen=True, slots=True)
class SquadAction:
    chip: DecisionChip
    transfers: tuple[TransferMove, ...]
    squad: tuple[CandidatePlayer, ...]
    bank_after_tenths: int
    hit_points: int


def rational_from_fraction(value: Fraction) -> RationalValue:
    return RationalValue(value.numerator, value.denominator)


def action_objective(action: DecisionAction) -> Fraction:
    value = action.mechanics.objective_points
    return Fraction(value.numerator, value.denominator)


def chip_set_for_gameweek(gameweek: int, *, ruleset: RuleSet) -> int:
    if gameweek <= ruleset.integer("FPL-CHIP-FIRST-SET-LAST-GW-001"):
        return 1
    if gameweek >= ruleset.integer("FPL-CHIP-SECOND-SET-FIRST-GW-001"):
        return 2
    raise ValueError(f"gameweek {gameweek} is outside configured chip sets")


def available_chips(state: DeadlineStateView, *, ruleset: RuleSet) -> set[DecisionChip]:
    available = {DecisionChip.NONE}
    set_number = chip_set_for_gameweek(state.gameweek, ruleset=ruleset)
    used = {(row.chip, row.set_number) for row in state.chips_used}
    mapping = {
        DecisionChip.TRIPLE_CAPTAIN: "TRIPLE_CAPTAIN",
        DecisionChip.BENCH_BOOST: "BENCH_BOOST",
        DecisionChip.WILDCARD: "WILDCARD",
        DecisionChip.FREE_HIT: "FREE_HIT",
    }
    for chip, ledger_name in mapping.items():
        if (ledger_name, set_number) not in used:
            available.add(chip)

    if state.gameweek in set(ruleset.value("FPL-FREE-HIT-DISALLOWED-GWS-001")):
        available.discard(DecisionChip.FREE_HIT)
    if state.gameweek in set(ruleset.value("FPL-WILDCARD-DISALLOWED-GWS-001")):
        available.discard(DecisionChip.WILDCARD)
    boundary = ruleset.mapping("FPL-FREE-HIT-CROSS-HALF-CONSECUTIVE-001")
    if (
        boundary.get("allowed") is False
        and state.gameweek == int(boundary["second_half_gw"])
    ):
        first = int(boundary["first_half_gw"])
        if any(
            row.chip == "FREE_HIT" and row.gameweek == first
            for row in state.chips_used
        ):
            available.discard(DecisionChip.FREE_HIT)
    return available


def candidate_map(universe: CandidateUniverse) -> dict[OfficialPlayerId, CandidatePlayer]:
    return {row.player_id: row for row in universe.players}


def validate_owned_against_universe(
    state: DeadlineStateView,
    universe: CandidateUniverse,
) -> None:
    candidates = candidate_map(universe)
    errors: list[str] = []
    for owned in state.squad:
        candidate = candidates.get(owned.player_id)
        if candidate is None:
            errors.append(f"owned player {owned.player_id} is outside candidate universe")
            continue
        if candidate.team_id != owned.team_id:
            errors.append(f"owned player {owned.player_id} team mismatch")
        if candidate.position != owned.position:
            errors.append(f"owned player {owned.player_id} position mismatch")
        if candidate.current_price_tenths != owned.current_price_tenths:
            errors.append(f"owned player {owned.player_id} current price mismatch")
    if errors:
        raise ValueError("; ".join(errors))


def _legal_squad(players: tuple[CandidatePlayer, ...], *, ruleset: RuleSet) -> bool:
    return not ruleset.validate_squad(
        positions=(row.position for row in players),
        club_ids=(row.team_id for row in players),
        prices_tenths=(row.current_price_tenths for row in players),
        enforce_budget=False,
    )


def _hit_points(transfer_count: int, state: DeadlineStateView, *, ruleset: RuleSet) -> int:
    extra = max(0, transfer_count - state.free_transfers)
    return extra * ruleset.integer("FPL-EXTRA-TRANSFER-HIT-POINTS-001")


def _incoming_combinations(
    outgoing: tuple[OwnedPlayer, ...],
    *,
    universe: CandidateUniverse,
    owned_ids: set[OfficialPlayerId],
):
    counts = {position: 0 for position in ("GK", "DEF", "MID", "FWD")}
    for row in outgoing:
        counts[row.position] += 1
    pools = {
        position: tuple(
            row
            for row in universe.players
            if row.position == position and row.player_id not in owned_ids
        )
        for position in counts
    }
    position_choices = []
    for position in ("GK", "DEF", "MID", "FWD"):
        count = counts[position]
        if count:
            position_choices.append(tuple(combinations(pools[position], count)))
    if not position_choices:
        yield ()
        return
    for grouped in product(*position_choices):
        yield tuple(player for group in grouped for player in group)


def _pair_transfers(
    outgoing: tuple[OwnedPlayer, ...],
    incoming: tuple[CandidatePlayer, ...],
) -> tuple[TransferMove, ...]:
    moves: list[TransferMove] = []
    for position in ("GK", "DEF", "MID", "FWD"):
        outgoing_ids = sorted(row.player_id for row in outgoing if row.position == position)
        incoming_ids = sorted(row.player_id for row in incoming if row.position == position)
        if len(outgoing_ids) != len(incoming_ids):
            raise ValueError("transfer position counts do not reconcile")
        moves.extend(
            TransferMove(out_player, in_player)
            for out_player, in_player in zip(outgoing_ids, incoming_ids, strict=True)
        )
    return tuple(sorted(moves))


def normal_squad_actions(
    *,
    state: DeadlineStateView,
    universe: CandidateUniverse,
    chip: DecisionChip,
    max_transfers: int,
    ruleset: RuleSet,
):
    if isinstance(max_transfers, bool) or not isinstance(max_transfers, int) or not 0 <= max_transfers <= 15:
        raise ValueError("max_transfers must be an integer in [0,15]")
    candidate_by_id = candidate_map(universe)
    current = tuple(candidate_by_id[row.player_id] for row in state.squad)
    owned_ids = {row.player_id for row in state.squad}
    for transfer_count in range(max_transfers + 1):
        for outgoing in combinations(state.squad, transfer_count):
            outgoing = tuple(outgoing)
            outgoing_ids = {row.player_id for row in outgoing}
            retained = tuple(row for row in current if row.player_id not in outgoing_ids)
            sale_value = sum(row.selling_price_tenths for row in outgoing)
            for incoming in _incoming_combinations(
                outgoing,
                universe=universe,
                owned_ids=owned_ids,
            ):
                incoming_cost = sum(row.current_price_tenths for row in incoming)
                bank_after = state.bank_tenths + sale_value - incoming_cost
                if bank_after < 0:
                    continue
                squad = tuple(
                    sorted((*retained, *incoming), key=lambda row: int(row.player_id))
                )
                if not _legal_squad(squad, ruleset=ruleset):
                    continue
                yield SquadAction(
                    chip=chip,
                    transfers=_pair_transfers(outgoing, incoming),
                    squad=squad,
                    bank_after_tenths=bank_after,
                    hit_points=_hit_points(transfer_count, state, ruleset=ruleset),
                )


def full_rebuild_squad_actions(
    *,
    state: DeadlineStateView,
    universe: CandidateUniverse,
    chip: DecisionChip,
    ruleset: RuleSet,
):
    if chip not in {DecisionChip.WILDCARD, DecisionChip.FREE_HIT}:
        raise ValueError("full rebuild action requires Wildcard or Free Hit")
    counts_raw = ruleset.mapping("FPL-SQUAD-POSITIONS-001")
    counts = {position: int(value) for position, value in counts_raw.items()}
    owned = {row.player_id: row for row in state.squad}
    budget = state.bank_tenths + sum(row.selling_price_tenths for row in state.squad)
    by_position = {
        position: tuple(row for row in universe.players if row.position == position)
        for position in ("GK", "DEF", "MID", "FWD")
    }
    choice_groups = [
        combinations(by_position[position], counts[position])
        for position in ("GK", "DEF", "MID", "FWD")
    ]
    current_ids = set(owned)
    for grouped in product(*choice_groups):
        squad = tuple(
            sorted(
                (player for group in grouped for player in group),
                key=lambda row: int(row.player_id),
            )
        )
        club_counts: dict[int, int] = {}
        for player in squad:
            club_counts[player.team_id] = club_counts.get(player.team_id, 0) + 1
        if max(club_counts.values(), default=0) > ruleset.integer("FPL-SQUAD-MAX-CLUB-001"):
            continue
        cost = sum(
            owned[player.player_id].selling_price_tenths
            if player.player_id in owned
            else player.current_price_tenths
            for player in squad
        )
        if cost > budget or not _legal_squad(squad, ruleset=ruleset):
            continue
        selected_ids = {row.player_id for row in squad}
        outgoing = tuple(row for row in state.squad if row.player_id not in selected_ids)
        incoming = tuple(row for row in squad if row.player_id not in current_ids)
        transfers = _pair_transfers(outgoing, incoming)
        bank_during = budget - cost
        bank_after = state.bank_tenths if chip is DecisionChip.FREE_HIT else bank_during
        yield SquadAction(
            chip=chip,
            transfers=transfers,
            squad=squad,
            bank_after_tenths=bank_after,
            hit_points=0,
        )


def decision_action(
    squad_action: SquadAction,
    *,
    values: dict[OfficialPlayerId, PlayerGameweekValue],
    ruleset: RuleSet,
) -> DecisionAction:
    squad_ids = tuple(row.player_id for row in squad_action.squad)
    squad_values = {player_id: values[player_id] for player_id in squad_ids}
    submission = optimise_squad_submission(
        squad_action.squad,
        squad_values,
        chip=squad_action.chip,
        hit_points=squad_action.hit_points,
        ruleset=ruleset,
    )
    return DecisionAction(
        chip=squad_action.chip,
        transfers=squad_action.transfers,
        squad_ids=squad_ids,
        xi_ids=submission.xi_ids,
        captain_id=submission.captain_id,
        vice_captain_id=submission.vice_captain_id,
        bench_gk_id=submission.bench_gk_id,
        outfield_bench_order=submission.outfield_bench_order,
        bank_after_tenths=squad_action.bank_after_tenths,
        mechanics=submission.mechanics,
    )


def action_tie_key(action: DecisionAction) -> tuple:
    chip_rank = {
        DecisionChip.NONE: 4,
        DecisionChip.TRIPLE_CAPTAIN: 3,
        DecisionChip.BENCH_BOOST: 2,
        DecisionChip.WILDCARD: 1,
        DecisionChip.FREE_HIT: 0,
    }
    return (
        -len(action.transfers),
        chip_rank[action.chip],
        tuple(-int(player_id) for player_id in action.squad_ids),
        tuple(-int(player_id) for player_id in action.xi_ids),
        -int(action.captain_id),
        -int(action.vice_captain_id),
    )


def enumerate_gameweek_actions(
    *,
    state: DeadlineStateView,
    forecast: Forecast,
    universe: CandidateUniverse,
    ruleset: RuleSet,
    max_normal_transfers: int,
    chips_considered: tuple[DecisionChip, ...],
):
    """Yield every legal action in the declared one-deadline surface."""

    validate_owned_against_universe(state, universe)
    values = build_gameweek_values(
        forecast,
        gameweek=state.gameweek,
        player_ids=(row.player_id for row in universe.players),
    )
    available = available_chips(state, ruleset=ruleset)
    considered = tuple(sorted(set(chips_considered), key=lambda chip: chip.value))
    for chip in considered:
        if chip not in available:
            continue
        squad_actions = (
            full_rebuild_squad_actions(
                state=state,
                universe=universe,
                chip=chip,
                ruleset=ruleset,
            )
            if chip in {DecisionChip.WILDCARD, DecisionChip.FREE_HIT}
            else normal_squad_actions(
                state=state,
                universe=universe,
                chip=chip,
                max_transfers=max_normal_transfers,
                ruleset=ruleset,
            )
        )
        for squad_action in squad_actions:
            yield decision_action(squad_action, values=values, ruleset=ruleset)


def action_surface_complete(
    *,
    max_normal_transfers: int,
    chips_considered: tuple[DecisionChip, ...],
    available: set[DecisionChip],
) -> bool:
    return max_normal_transfers == 15 and available.issubset(set(chips_considered))
