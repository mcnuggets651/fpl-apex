"""Exhaustive reference DecisionEngine for one current FPL gameweek.

This engine is intentionally correctness-first. It completely enumerates the declared
candidate universe and declared action surface, then exhaustively optimises submission
mechanics for each legal resulting squad. Its exactness certificate makes any narrower
universe/action surface visible instead of pretending it is a global optimum.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations, product

from apex_fpl.core.decision import (
    CandidatePlayer,
    CandidateUniverse,
    CandidateUniverseScope,
    DecisionAction,
    DecisionChip,
    DecisionInput,
    DecisionObjectiveModel,
    DecisionResult,
    DecisionUseMode,
    ExactnessClaim,
    ExactnessStatus,
    ExpansionResult,
    RationalValue,
    SolverCertificate,
    SolverStatus,
    TransferMove,
)
from apex_fpl.core.forecast import Forecast, ForecastUseMode
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.manager_state import ManagerState
from apex_fpl.core.rules import RuleSet

from .mechanics import PlayerGameweekValue, build_gameweek_values, optimise_squad_submission


@dataclass(frozen=True, slots=True)
class _SquadAction:
    chip: DecisionChip
    transfers: tuple[TransferMove, ...]
    squad: tuple[CandidatePlayer, ...]
    bank_after_tenths: int
    hit_points: int


def _fraction(numerator: int, denominator: int) -> Fraction:
    return Fraction(numerator, denominator)


def _rational(value: Fraction) -> RationalValue:
    return RationalValue(value.numerator, value.denominator)


def _objective(action: DecisionAction) -> Fraction:
    return _fraction(
        action.mechanics.objective_points.numerator,
        action.mechanics.objective_points.denominator,
    )


def _chip_set_for_gameweek(gameweek: int, *, ruleset: RuleSet) -> int:
    if gameweek <= ruleset.integer("FPL-CHIP-FIRST-SET-LAST-GW-001"):
        return 1
    if gameweek >= ruleset.integer("FPL-CHIP-SECOND-SET-FIRST-GW-001"):
        return 2
    raise ValueError(f"gameweek {gameweek} is outside configured chip sets")


def _available_chips(state: ManagerState, *, ruleset: RuleSet) -> set[DecisionChip]:
    available = {DecisionChip.NONE}
    set_number = _chip_set_for_gameweek(state.gameweek, ruleset=ruleset)
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


def _candidate_map(universe: CandidateUniverse) -> dict[OfficialPlayerId, CandidatePlayer]:
    return {row.player_id: row for row in universe.players}


def _validate_owned_against_universe(
    state: ManagerState,
    universe: CandidateUniverse,
) -> None:
    candidates = _candidate_map(universe)
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


def _hit_points(transfer_count: int, state: ManagerState, *, ruleset: RuleSet) -> int:
    extra = max(0, transfer_count - state.free_transfers)
    return extra * ruleset.integer("FPL-EXTRA-TRANSFER-HIT-POINTS-001")


def _incoming_combinations(
    outgoing: tuple,
    *,
    universe: CandidateUniverse,
    owned_ids: set[OfficialPlayerId],
):
    counts: dict[str, int] = {
        position: 0 for position in ("GK", "DEF", "MID", "FWD")
    }
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
    outgoing: tuple,
    incoming: tuple[CandidatePlayer, ...],
) -> tuple[TransferMove, ...]:
    moves: list[TransferMove] = []
    for position in ("GK", "DEF", "MID", "FWD"):
        outgoing_ids = sorted(
            row.player_id for row in outgoing if row.position == position
        )
        incoming_ids = sorted(
            row.player_id for row in incoming if row.position == position
        )
        if len(outgoing_ids) != len(incoming_ids):
            raise ValueError("transfer position counts do not reconcile")
        moves.extend(
            TransferMove(out_player, in_player)
            for out_player, in_player in zip(
                outgoing_ids,
                incoming_ids,
                strict=True,
            )
        )
    return tuple(sorted(moves))


def _normal_squad_actions(
    *,
    state: ManagerState,
    universe: CandidateUniverse,
    chip: DecisionChip,
    max_transfers: int,
    ruleset: RuleSet,
):
    candidate_by_id = _candidate_map(universe)
    current = tuple(candidate_by_id[row.player_id] for row in state.squad)
    owned_ids = {row.player_id for row in state.squad}
    for transfer_count in range(max_transfers + 1):
        for outgoing in combinations(state.squad, transfer_count):
            outgoing_ids = {row.player_id for row in outgoing}
            retained = tuple(
                row for row in current if row.player_id not in outgoing_ids
            )
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
                    sorted(
                        (*retained, *incoming),
                        key=lambda row: int(row.player_id),
                    )
                )
                if not _legal_squad(squad, ruleset=ruleset):
                    continue
                yield _SquadAction(
                    chip=chip,
                    transfers=_pair_transfers(outgoing, incoming),
                    squad=squad,
                    bank_after_tenths=bank_after,
                    hit_points=_hit_points(
                        transfer_count,
                        state,
                        ruleset=ruleset,
                    ),
                )


def _full_rebuild_squads(
    *,
    state: ManagerState,
    universe: CandidateUniverse,
    chip: DecisionChip,
    ruleset: RuleSet,
):
    counts_raw = ruleset.mapping("FPL-SQUAD-POSITIONS-001")
    counts = {position: int(value) for position, value in counts_raw.items()}
    owned = {row.player_id: row for row in state.squad}
    budget = state.bank_tenths + sum(
        row.selling_price_tenths for row in state.squad
    )
    by_position = {
        position: tuple(
            row for row in universe.players if row.position == position
        )
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
        if max(club_counts.values(), default=0) > ruleset.integer(
            "FPL-SQUAD-MAX-CLUB-001"
        ):
            continue
        cost = sum(
            owned[player.player_id].selling_price_tenths
            if player.player_id in owned
            else player.current_price_tenths
            for player in squad
        )
        if cost > budget:
            continue
        if not _legal_squad(squad, ruleset=ruleset):
            continue
        selected_ids = {row.player_id for row in squad}
        outgoing = tuple(
            row for row in state.squad if row.player_id not in selected_ids
        )
        incoming = tuple(
            row for row in squad if row.player_id not in current_ids
        )
        transfers = _pair_transfers(outgoing, incoming)
        bank_during = budget - cost
        bank_after = (
            state.bank_tenths
            if chip is DecisionChip.FREE_HIT
            else bank_during
        )
        yield _SquadAction(
            chip=chip,
            transfers=transfers,
            squad=squad,
            bank_after_tenths=bank_after,
            hit_points=0,
        )


def _decision_action(
    squad_action: _SquadAction,
    *,
    values: dict[OfficialPlayerId, PlayerGameweekValue],
    ruleset: RuleSet,
) -> DecisionAction:
    squad_ids = tuple(row.player_id for row in squad_action.squad)
    squad_values = {
        player_id: values[player_id] for player_id in squad_ids
    }
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


def _action_tie_key(action: DecisionAction) -> tuple:
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


def _surface_complete(
    decision_input: DecisionInput,
    *,
    available_chips: set[DecisionChip],
) -> bool:
    return (
        decision_input.max_normal_transfers == 15
        and available_chips.issubset(set(decision_input.chips_considered))
    )


def optimise_current_gameweek(
    *,
    state: ManagerState,
    forecast: Forecast,
    universe: CandidateUniverse,
    ruleset: RuleSet,
    use_mode: DecisionUseMode,
    max_normal_transfers: int,
    chips_considered: tuple[DecisionChip, ...] = (DecisionChip.NONE,),
    alternatives_limit: int = 5,
) -> DecisionResult:
    """Return the maximum marginal-EV legal action over the declared search surface."""

    state.require_decision_safe(ruleset=ruleset)
    if state.gameweek <= 0:
        raise ValueError("DecisionEngine requires a positive current gameweek")
    if forecast.season != state.season or ruleset.season != state.season:
        raise ValueError("decision season mismatch")
    if (
        forecast.ruleset_id != ruleset.ruleset_id
        or state.ruleset_id != ruleset.ruleset_id
    ):
        raise ValueError("decision RuleSet identity mismatch")
    if universe.global_world_id != forecast.global_world_id:
        raise ValueError("candidate universe GlobalWorldId does not match Forecast")
    _validate_owned_against_universe(state, universe)
    if use_mode is DecisionUseMode.PRODUCTION:
        if (
            forecast.use_mode is not ForecastUseMode.PRODUCTION
            or not forecast.production_eligible
        ):
            raise ValueError(
                "production decision requires a production-eligible Forecast"
            )
        if forecast.abstentions:
            raise ValueError(
                "production decision cannot consume Forecast abstentions"
            )

    available_chips = _available_chips(state, ruleset=ruleset)
    considered = tuple(
        sorted(set(chips_considered), key=lambda chip: chip.value)
    )
    decision_input = DecisionInput(
        manager_state_id=state.manager_state_id,
        forecast_id=forecast.forecast_id,
        ruleset_id=ruleset.ruleset_id,
        candidate_universe_id=universe.candidate_universe_id,
        gameweek=state.gameweek,
        use_mode=use_mode,
        objective_model=DecisionObjectiveModel.MARGINAL_INDEPENDENCE_BASELINE,
        max_normal_transfers=max_normal_transfers,
        chips_considered=considered,
    )
    values = build_gameweek_values(
        forecast,
        gameweek=state.gameweek,
        player_ids=(row.player_id for row in universe.players),
    )

    legal_actions: list[DecisionAction] = []
    for chip in decision_input.chips_considered:
        if chip not in available_chips:
            continue
        if chip in {DecisionChip.WILDCARD, DecisionChip.FREE_HIT}:
            squad_actions = _full_rebuild_squads(
                state=state,
                universe=universe,
                chip=chip,
                ruleset=ruleset,
            )
        else:
            squad_actions = _normal_squad_actions(
                state=state,
                universe=universe,
                chip=chip,
                max_transfers=decision_input.max_normal_transfers,
                ruleset=ruleset,
            )
        for squad_action in squad_actions:
            legal_actions.append(
                _decision_action(
                    squad_action,
                    values=values,
                    ruleset=ruleset,
                )
            )
    if not legal_actions:
        raise ValueError(
            "DecisionEngine found no legal actions in declared search surface"
        )

    legal_actions.sort(
        key=lambda action: (_objective(action), _action_tie_key(action)),
        reverse=True,
    )
    selected = legal_actions[0]
    alternatives = tuple(
        legal_actions[1 : 1 + max(0, alternatives_limit)]
    )
    incumbent_fraction = _objective(selected)
    incumbent = _rational(incumbent_fraction)
    zero = RationalValue.zero()
    solver = SolverCertificate(
        status=SolverStatus.OPTIMAL,
        incumbent_objective=incumbent,
        best_bound=incumbent,
        gap=zero,
        numeric_error_bound=zero,
        message="exhaustive reference enumeration completed",
    )

    action_surface_complete = _surface_complete(
        decision_input,
        available_chips=available_chips,
    )
    reasons: list[str] = []
    if universe.scope is not CandidateUniverseScope.FULL_OFFICIAL:
        reasons.append(
            "candidate universe is scoped and has no successful expansion certificate"
        )
    if not action_surface_complete:
        missing_chips = sorted(
            chip.value
            for chip in available_chips - set(decision_input.chips_considered)
        )
        if decision_input.max_normal_transfers < 15:
            reasons.append(
                "normal transfer surface capped at "
                f"{decision_input.max_normal_transfers}/15"
            )
        if missing_chips:
            reasons.append(
                "available chips omitted from action surface: "
                + ",".join(missing_chips)
            )

    status = (
        ExactnessStatus.GLOBAL_OPTIMAL
        if (
            universe.scope is CandidateUniverseScope.FULL_OFFICIAL
            and action_surface_complete
        )
        else ExactnessStatus.FEASIBLE_INCUMBENT
    )
    exactness = ExactnessClaim(
        status=status,
        candidate_universe_id=universe.candidate_universe_id,
        universe_scope=universe.scope,
        solver_status=solver.status,
        action_surface_complete=action_surface_complete,
        search_complete=True,
        best_bound=solver.best_bound,
        gap=solver.gap,
        filter_identity=universe.filter_identity,
        expansion_result=ExpansionResult.NOT_RUN,
        expansion_certificate_id=None,
        numeric_error_bound=solver.numeric_error_bound,
        reasons=tuple(reasons),
    )
    if (
        use_mode is DecisionUseMode.PRODUCTION
        and not exactness.publication_exactness_eligible
    ):
        raise ValueError(
            "production DecisionEngine exactness is not publication eligible: "
            + "; ".join(exactness.reasons)
        )
    return DecisionResult(
        decision_input=decision_input,
        selected_action=selected,
        alternatives=alternatives,
        solver=solver,
        exactness=exactness,
        enumerated_actions=len(legal_actions),
    )
