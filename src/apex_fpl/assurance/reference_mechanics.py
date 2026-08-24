"""Independent reference legality and expected-mechanics checker for one sealed decision.

This module intentionally does not import ``apex_fpl.decision.engine`` or
``apex_fpl.decision.mechanics``.  It re-derives the submitted action from core contracts
and uses exhaustive realised appearance states for autosubs instead of the production
mechanics dynamic program.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product

from apex_fpl.core.assurance import (
    ReferenceCheckResult,
    ReferenceMechanicsCertificate,
    ReferenceMechanicsCheck,
)
from apex_fpl.core.decision import (
    CandidateUniverse,
    DecisionAction,
    DecisionChip,
    DecisionMechanics,
    DecisionResult,
    RationalValue,
)
from apex_fpl.core.forecast import Forecast, PROBABILITY_DENOMINATOR
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.manager_state import ManagerState
from apex_fpl.core.rules import RuleSet


REFERENCE_MECHANICS_ALGORITHM_ID = "reference-mechanics-exhaustive-appearance-v1"
_OUTFIELD = ("DEF", "MID", "FWD")


@dataclass(frozen=True, slots=True)
class _PlayerValue:
    expected_points: Fraction
    appearance_probability: Fraction


def _rv(value: Fraction) -> RationalValue:
    return RationalValue(value.numerator, value.denominator)


def _result(
    check: ReferenceMechanicsCheck,
    passed: bool,
    *,
    passed_detail: str,
    failed_detail: str,
) -> ReferenceCheckResult:
    return ReferenceCheckResult(
        check=check,
        passed=passed,
        detail=passed_detail if passed else failed_detail,
    )


def _chip_set(gameweek: int, ruleset: RuleSet) -> int:
    if gameweek <= ruleset.integer("FPL-CHIP-FIRST-SET-LAST-GW-001"):
        return 1
    if gameweek >= ruleset.integer("FPL-CHIP-SECOND-SET-FIRST-GW-001"):
        return 2
    raise ValueError(f"gameweek {gameweek} is outside configured chip sets")


def _chip_available(chip: DecisionChip, state: ManagerState, ruleset: RuleSet) -> bool:
    if chip is DecisionChip.NONE:
        return True
    set_number = _chip_set(state.gameweek, ruleset)
    ledger_name = {
        DecisionChip.TRIPLE_CAPTAIN: "TRIPLE_CAPTAIN",
        DecisionChip.BENCH_BOOST: "BENCH_BOOST",
        DecisionChip.WILDCARD: "WILDCARD",
        DecisionChip.FREE_HIT: "FREE_HIT",
    }[chip]
    if any(row.chip == ledger_name and row.set_number == set_number for row in state.chips_used):
        return False
    if chip is DecisionChip.FREE_HIT:
        if state.gameweek in set(ruleset.value("FPL-FREE-HIT-DISALLOWED-GWS-001")):
            return False
        boundary = ruleset.mapping("FPL-FREE-HIT-CROSS-HALF-CONSECUTIVE-001")
        if boundary.get("allowed") is False and state.gameweek == int(boundary["second_half_gw"]):
            first = int(boundary["first_half_gw"])
            if any(row.chip == "FREE_HIT" and row.gameweek == first for row in state.chips_used):
                return False
    if chip is DecisionChip.WILDCARD and state.gameweek in set(
        ruleset.value("FPL-WILDCARD-DISALLOWED-GWS-001")
    ):
        return False
    return True


def _gameweek_values(
    forecast: Forecast,
    *,
    gameweek: int,
    player_ids: tuple[OfficialPlayerId, ...],
) -> dict[OfficialPlayerId, _PlayerValue]:
    requested = set(player_ids)
    abstained = {
        row.target.player_id
        for row in forecast.abstentions
        if row.target.gameweek == gameweek and row.target.player_id in requested
    }
    if abstained:
        raise ValueError(
            "reference mechanics cannot neutral-fill forecast abstentions: "
            + ",".join(str(item) for item in sorted(abstained))
        )
    rows_by_player: dict[OfficialPlayerId, list] = {player_id: [] for player_id in requested}
    for row in forecast.rows:
        if row.target.gameweek == gameweek and row.target.player_id in rows_by_player:
            rows_by_player[row.target.player_id].append(row)

    values: dict[OfficialPlayerId, _PlayerValue] = {}
    for player_id, rows in rows_by_player.items():
        expected = Fraction(0, 1)
        no_appearance = Fraction(1, 1)
        for row in rows:
            expected += Fraction(row.expected_points_numerator, PROBABILITY_DENOMINATOR)
            p_zero = Fraction(
                row.minutes_distribution.probability_exactly(0),
                PROBABILITY_DENOMINATOR,
            )
            no_appearance *= p_zero
        appearance = Fraction(0, 1) if not rows else 1 - no_appearance
        values[player_id] = _PlayerValue(expected, appearance)
    return values


def _legal_counts(counts: dict[str, int], ruleset: RuleSet) -> bool:
    minimum = ruleset.mapping("FPL-XI-POSITION-MIN-001")
    maximum = ruleset.mapping("FPL-XI-POSITION-MAX-001")
    return all(
        int(minimum[position]) <= counts[position] <= int(maximum[position])
        for position in _OUTFIELD
    )


def _selected_outfield_subs(
    action: DecisionAction,
    *,
    positions: dict[OfficialPlayerId, str],
    appeared: set[OfficialPlayerId],
    ruleset: RuleSet,
) -> tuple[OfficialPlayerId, ...]:
    starters = tuple(player_id for player_id in action.xi_ids if positions[player_id] != "GK")
    missing = {
        position: sum(
            positions[player_id] == position and player_id not in appeared
            for player_id in starters
        )
        for position in _OUTFIELD
    }
    planned = {
        position: sum(positions[player_id] == position for player_id in starters)
        for position in _OUTFIELD
    }
    # Each state is (remaining missing slots, hypothetical full-formation counts).
    states: set[tuple[tuple[int, int, int], tuple[int, int, int]]] = {
        (
            tuple(missing[position] for position in _OUTFIELD),
            tuple(planned[position] for position in _OUTFIELD),
        )
    }
    selected: list[OfficialPlayerId] = []
    for bench_player in action.outfield_bench_order:
        if bench_player not in appeared:
            continue
        bench_position = positions[bench_player]
        next_states: set[tuple[tuple[int, int, int], tuple[int, int, int]]] = set()
        for missing_tuple, counts_tuple in states:
            remaining = dict(zip(_OUTFIELD, missing_tuple, strict=True))
            counts = dict(zip(_OUTFIELD, counts_tuple, strict=True))
            for missing_position in _OUTFIELD:
                if remaining[missing_position] <= 0:
                    continue
                trial_remaining = dict(remaining)
                trial_counts = dict(counts)
                trial_remaining[missing_position] -= 1
                trial_counts[missing_position] -= 1
                trial_counts[bench_position] += 1
                if not _legal_counts(trial_counts, ruleset):
                    continue
                next_states.add(
                    (
                        tuple(trial_remaining[position] for position in _OUTFIELD),
                        tuple(trial_counts[position] for position in _OUTFIELD),
                    )
                )
        # Bench priority is absolute: if this player can legally occupy any missing slot,
        # retain only states where that player comes on. Slot identities are abstract.
        if next_states:
            selected.append(bench_player)
            states = next_states
    return tuple(selected)


def _autosub_expectation(
    action: DecisionAction,
    *,
    values: dict[OfficialPlayerId, _PlayerValue],
    positions: dict[OfficialPlayerId, str],
    ruleset: RuleSet,
) -> Fraction:
    uncertain = tuple(
        player_id
        for player_id in action.squad_ids
        if values[player_id].appearance_probability not in {Fraction(0, 1), Fraction(1, 1)}
    )
    fixed_appeared = {
        player_id
        for player_id in action.squad_ids
        if values[player_id].appearance_probability == 1
    }
    total = Fraction(0, 1)
    for bits in product((0, 1), repeat=len(uncertain)):
        appeared = set(fixed_appeared)
        probability = Fraction(1, 1)
        for player_id, bit in zip(uncertain, bits, strict=True):
            p = values[player_id].appearance_probability
            probability *= p if bit else 1 - p
            if bit:
                appeared.add(player_id)
        if probability == 0:
            continue
        substituted: list[OfficialPlayerId] = []
        starting_gk = next(
            player_id for player_id in action.xi_ids if positions[player_id] == "GK"
        )
        if starting_gk not in appeared and action.bench_gk_id in appeared:
            substituted.append(action.bench_gk_id)
        substituted.extend(
            _selected_outfield_subs(
                action,
                positions=positions,
                appeared=appeared,
                ruleset=ruleset,
            )
        )
        conditional_points = Fraction(0, 1)
        for player_id in substituted:
            p = values[player_id].appearance_probability
            if p <= 0:
                raise ValueError("selected substitute has zero appearance probability")
            conditional_points += values[player_id].expected_points / p
        total += probability * conditional_points
    return total


def _reference_mechanics(
    action: DecisionAction,
    *,
    forecast: Forecast,
    ruleset: RuleSet,
    positions: dict[OfficialPlayerId, str],
    hit_points: int,
    gameweek: int,
) -> DecisionMechanics:
    values = _gameweek_values(forecast, gameweek=gameweek, player_ids=action.squad_ids)
    expected = {player_id: row.expected_points for player_id, row in values.items()}
    xi_points = sum((expected[player_id] for player_id in action.xi_ids), Fraction(0, 1))
    total_squad_points = sum(expected.values(), Fraction(0, 1))
    captain_multiplier = (
        ruleset.integer("FPL-TRIPLE-CAPTAIN-MULTIPLIER-001")
        if action.chip is DecisionChip.TRIPLE_CAPTAIN
        else ruleset.integer("FPL-CAPTAIN-MULTIPLIER-001")
    )
    captain = values[action.captain_id]
    vice = values[action.vice_captain_id]
    captain_bonus = (captain_multiplier - 1) * (
        captain.expected_points + (1 - captain.appearance_probability) * vice.expected_points
    )
    if action.chip is DecisionChip.BENCH_BOOST:
        autosub = Fraction(0, 1)
        before_hits = total_squad_points + captain_bonus
    else:
        autosub = _autosub_expectation(
            action,
            values=values,
            positions=positions,
            ruleset=ruleset,
        )
        before_hits = xi_points + autosub + captain_bonus
    return DecisionMechanics(
        xi_points=_rv(xi_points),
        autosub_points=_rv(autosub),
        captain_bonus=_rv(captain_bonus),
        squad_points_if_bench_boost=_rv(total_squad_points),
        points_before_hits=_rv(before_hits),
        hit_points=hit_points,
        objective_points=_rv(before_hits - hit_points),
    )


def certify_selected_action(
    result: DecisionResult,
    *,
    state: ManagerState,
    forecast: Forecast,
    universe: CandidateUniverse,
    ruleset: RuleSet,
    additional_source_artifact_ids: tuple[str, ...] = (),
) -> ReferenceMechanicsCertificate:
    """Independently reconcile the exact selected action against sealed core inputs."""

    action = result.selected_action
    checks: dict[ReferenceMechanicsCheck, ReferenceCheckResult] = {}

    identity_ok = (
        result.decision_input.manager_state_id == state.manager_state_id
        and result.decision_input.forecast_id == forecast.forecast_id
        and result.decision_input.ruleset_id == ruleset.ruleset_id
        and result.decision_input.candidate_universe_id == universe.candidate_universe_id
        and result.decision_input.gameweek == state.gameweek
        and state.ruleset_id == ruleset.ruleset_id
        and forecast.ruleset_id == ruleset.ruleset_id
        and state.season == forecast.season == ruleset.season
        and universe.global_world_id == forecast.global_world_id
    )
    checks[ReferenceMechanicsCheck.INPUT_IDENTITY] = _result(
        ReferenceMechanicsCheck.INPUT_IDENTITY,
        identity_ok,
        passed_detail="sealed decision identities reconcile",
        failed_detail="sealed decision/state/forecast/universe/RuleSet identities do not reconcile",
    )

    try:
        state.require_decision_safe(ruleset=ruleset)
        state_ok = True
        state_detail = "ManagerState is CURRENT_EXACT and internally reconciled"
    except ValueError as exc:
        state_ok = False
        state_detail = str(exc)
    checks[ReferenceMechanicsCheck.STATE_CURRENT_EXACT] = ReferenceCheckResult(
        ReferenceMechanicsCheck.STATE_CURRENT_EXACT,
        state_ok,
        state_detail,
    )

    candidate_map = {row.player_id: row for row in universe.players}
    owned_ok = True
    owned_errors: list[str] = []
    for owned in state.squad:
        candidate = candidate_map.get(owned.player_id)
        if candidate is None:
            owned_ok = False
            owned_errors.append(f"owned player {int(owned.player_id)} outside universe")
            continue
        if (
            candidate.team_id != owned.team_id
            or candidate.position != owned.position
            or candidate.current_price_tenths != owned.current_price_tenths
        ):
            owned_ok = False
            owned_errors.append(f"owned player {int(owned.player_id)} candidate facts mismatch")
    checks[ReferenceMechanicsCheck.OWNED_UNIVERSE_MATCH] = ReferenceCheckResult(
        ReferenceMechanicsCheck.OWNED_UNIVERSE_MATCH,
        owned_ok,
        "owned players match candidate identity/team/position/price" if owned_ok else "; ".join(owned_errors),
    )

    chip_ok = (
        action.chip in set(result.decision_input.chips_considered)
        and _chip_available(action.chip, state, ruleset)
    )
    checks[ReferenceMechanicsCheck.CHIP_AVAILABLE] = _result(
        ReferenceMechanicsCheck.CHIP_AVAILABLE,
        chip_ok,
        passed_detail=f"{action.chip.value} is considered and available",
        failed_detail=f"{action.chip.value} is not both considered and available",
    )

    current_ids = set(state.player_ids)
    action_ids = set(action.squad_ids)
    outgoing_ids = current_ids - action_ids
    incoming_ids = action_ids - current_ids
    move_out = {row.outgoing_player_id for row in action.transfers}
    move_in = {row.incoming_player_id for row in action.transfers}
    normal_chip = action.chip in {
        DecisionChip.NONE,
        DecisionChip.TRIPLE_CAPTAIN,
        DecisionChip.BENCH_BOOST,
    }
    transfer_set_ok = (
        move_out == outgoing_ids
        and move_in == incoming_ids
        and len(action.transfers) == len(outgoing_ids) == len(incoming_ids)
        and (not normal_chip or len(action.transfers) <= result.decision_input.max_normal_transfers)
    )
    checks[ReferenceMechanicsCheck.TRANSFER_SET] = _result(
        ReferenceMechanicsCheck.TRANSFER_SET,
        transfer_set_ok,
        passed_detail="submitted transfer set exactly reconciles current and resulting squads",
        failed_detail="submitted transfer set does not reconcile squad delta/action surface",
    )

    transfer_positions_ok = True
    for move in action.transfers:
        try:
            outgoing_position = state.player(move.outgoing_player_id).position
            incoming_position = candidate_map[move.incoming_player_id].position
        except (KeyError, ValueError):
            transfer_positions_ok = False
            break
        if outgoing_position != incoming_position:
            transfer_positions_ok = False
            break
    checks[ReferenceMechanicsCheck.TRANSFER_POSITIONS] = _result(
        ReferenceMechanicsCheck.TRANSFER_POSITIONS,
        transfer_positions_ok,
        passed_detail="every transfer preserves FPL position",
        failed_detail="one or more transfers lack same-position identity",
    )

    action_candidates = []
    missing_candidates = []
    for player_id in action.squad_ids:
        candidate = candidate_map.get(player_id)
        if candidate is None:
            missing_candidates.append(int(player_id))
        else:
            action_candidates.append(candidate)
    squad_errors = (
        (f"missing candidate ids {missing_candidates}",)
        if missing_candidates
        else ruleset.validate_squad(
            positions=(row.position for row in action_candidates),
            club_ids=(row.team_id for row in action_candidates),
            prices_tenths=(row.current_price_tenths for row in action_candidates),
            enforce_budget=False,
        )
    )
    squad_ok = not squad_errors
    checks[ReferenceMechanicsCheck.SQUAD_LEGAL] = ReferenceCheckResult(
        ReferenceMechanicsCheck.SQUAD_LEGAL,
        squad_ok,
        "resulting squad is RuleSet-legal" if squad_ok else "; ".join(squad_errors),
    )

    sale_value = sum(
        state.player(player_id).selling_price_tenths
        for player_id in outgoing_ids
        if player_id in current_ids
    )
    incoming_cost = sum(
        candidate_map[player_id].current_price_tenths
        for player_id in incoming_ids
        if player_id in candidate_map
    )
    bank_during = state.bank_tenths + sale_value - incoming_cost
    recomputed_bank = state.bank_tenths if action.chip is DecisionChip.FREE_HIT else bank_during
    finance_ok = (
        bank_during >= 0
        and action.bank_after_tenths == recomputed_bank
        and len(incoming_ids) == sum(player_id in candidate_map for player_id in incoming_ids)
    )
    checks[ReferenceMechanicsCheck.FINANCE] = _result(
        ReferenceMechanicsCheck.FINANCE,
        finance_ok,
        passed_detail=f"selling-resource bank reconciles exactly to {recomputed_bank} tenths",
        failed_detail=(
            f"selling-resource bank mismatch/insufficient funds calculated={recomputed_bank} "
            f"submitted={action.bank_after_tenths} temporary={bank_during}"
        ),
    )

    if action.chip in {DecisionChip.WILDCARD, DecisionChip.FREE_HIT}:
        expected_hit = 0
    else:
        expected_hit = max(0, len(action.transfers) - state.free_transfers) * ruleset.integer(
            "FPL-EXTRA-TRANSFER-HIT-POINTS-001"
        )
    hit_ok = action.mechanics.hit_points == expected_hit
    checks[ReferenceMechanicsCheck.HIT_COST] = _result(
        ReferenceMechanicsCheck.HIT_COST,
        hit_ok,
        passed_detail=f"hit cost reconciles exactly to {expected_hit}",
        failed_detail=f"hit cost {action.mechanics.hit_points} != independent {expected_hit}",
    )

    positions = {
        player_id: candidate_map[player_id].position
        for player_id in action.squad_ids
        if player_id in candidate_map
    }
    xi_errors = (
        ("XI player missing candidate identity",)
        if any(player_id not in positions for player_id in action.xi_ids)
        else ruleset.validate_lineup(positions=(positions[player_id] for player_id in action.xi_ids))
    )
    xi_ok = not xi_errors
    checks[ReferenceMechanicsCheck.XI_LEGAL] = ReferenceCheckResult(
        ReferenceMechanicsCheck.XI_LEGAL,
        xi_ok,
        "submitted XI is independently RuleSet-legal" if xi_ok else "; ".join(xi_errors),
    )

    bench = set(action.squad_ids) - set(action.xi_ids)
    bench_ok = (
        len(bench) == 4
        and action.bench_gk_id in bench
        and action.bench_gk_id in positions
        and positions[action.bench_gk_id] == "GK"
        and len(action.outfield_bench_order) == 3
        and set(action.outfield_bench_order) == bench - {action.bench_gk_id}
        and all(player_id in positions and positions[player_id] != "GK" for player_id in action.outfield_bench_order)
    )
    checks[ReferenceMechanicsCheck.BENCH_STRUCTURE] = _result(
        ReferenceMechanicsCheck.BENCH_STRUCTURE,
        bench_ok,
        passed_detail="bench goalkeeper and ordered outfield substitutes reconcile",
        failed_detail="bench structure is not independently legal",
    )

    captain_ok = (
        action.captain_id != action.vice_captain_id
        and action.captain_id in set(action.xi_ids)
        and action.vice_captain_id in set(action.xi_ids)
    )
    checks[ReferenceMechanicsCheck.CAPTAIN_VICE] = _result(
        ReferenceMechanicsCheck.CAPTAIN_VICE,
        captain_ok,
        passed_detail="captain and vice are distinct XI players",
        failed_detail="captain/vice structure is invalid",
    )

    recomputed_mechanics: DecisionMechanics | None = None
    mechanics_ok = False
    mechanics_detail = "reference mechanics prerequisites failed"
    if squad_ok and xi_ok and bench_ok and captain_ok and hit_ok:
        try:
            recomputed_mechanics = _reference_mechanics(
                action,
                forecast=forecast,
                ruleset=ruleset,
                positions=positions,
                hit_points=expected_hit,
                gameweek=result.decision_input.gameweek,
            )
            mechanics_ok = recomputed_mechanics == action.mechanics
            mechanics_detail = (
                "independent exhaustive-appearance mechanics exactly match DecisionAction"
                if mechanics_ok
                else "independent expected mechanics differ from DecisionAction"
            )
        except ValueError as exc:
            mechanics_detail = str(exc)
    checks[ReferenceMechanicsCheck.EXPECTED_MECHANICS] = ReferenceCheckResult(
        ReferenceMechanicsCheck.EXPECTED_MECHANICS,
        mechanics_ok,
        mechanics_detail,
    )

    artifacts = tuple(
        sorted(
            set(state.provenance_artifact_ids)
            | set(universe.source_artifact_ids)
            | set(additional_source_artifact_ids)
        )
    )
    return ReferenceMechanicsCertificate(
        decision_id=result.decision_id,
        decision_input_id=result.decision_input.decision_input_id,
        manager_state_id=state.manager_state_id,
        forecast_id=forecast.forecast_id,
        ruleset_id=ruleset.ruleset_id,
        candidate_universe_id=universe.candidate_universe_id,
        action_id=action.action_id,
        recomputed_bank_after_tenths=recomputed_bank,
        recomputed_hit_points=expected_hit,
        recomputed_mechanics=recomputed_mechanics,
        checks=tuple(checks[item] for item in ReferenceMechanicsCheck),
        algorithm_id=REFERENCE_MECHANICS_ALGORITHM_ID,
        source_artifact_ids=artifacts,
    )
