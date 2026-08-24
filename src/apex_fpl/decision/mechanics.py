"""Exact marginal-EV FPL submission mechanics for one fixed legal squad.

The football forecast supplies unconditional expected points and appearance probabilities.
This reference evaluator applies FPL XI/bench/captain mechanics exactly under the declared
marginal-independence baseline. Slice 9 later challenges that baseline with correlated
scenarios; Slice 8 never relabels it as correlation-aware truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations, permutations, product
from typing import Iterable

from apex_fpl.core.decision import CandidatePlayer, DecisionChip, DecisionMechanics, RationalValue
from apex_fpl.core.forecast import Forecast, PROBABILITY_DENOMINATOR
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.rules import RuleSet


@dataclass(frozen=True, slots=True)
class PlayerGameweekValue:
    player_id: OfficialPlayerId
    expected_points: Fraction
    appearance_probability: Fraction

    def __post_init__(self) -> None:
        if not 0 <= self.appearance_probability <= 1:
            raise ValueError("appearance probability must be in [0,1]")


@dataclass(frozen=True, slots=True)
class SquadSubmission:
    xi_ids: tuple[OfficialPlayerId, ...]
    captain_id: OfficialPlayerId
    vice_captain_id: OfficialPlayerId
    bench_gk_id: OfficialPlayerId
    outfield_bench_order: tuple[OfficialPlayerId, ...]
    mechanics: DecisionMechanics


def _rational(value: Fraction) -> RationalValue:
    return RationalValue(value.numerator, value.denominator)


def build_gameweek_values(
    forecast: Forecast,
    *,
    gameweek: int,
    player_ids: Iterable[OfficialPlayerId],
) -> dict[OfficialPlayerId, PlayerGameweekValue]:
    """Aggregate per-fixture forecast marginals into one gameweek value per player.

    Fixture-level no-appearance probabilities are multiplied to form the player's
    gameweek no-appearance probability. This is an explicit marginal independence
    assumption for double-gameweek fixture appearances, not a hidden certainty claim.
    """

    if isinstance(gameweek, bool) or not isinstance(gameweek, int) or gameweek <= 0:
        raise ValueError("gameweek must be a positive integer")
    requested = tuple(sorted(set(player_ids)))
    abstained = {
        row.target.player_id
        for row in forecast.abstentions
        if row.target.gameweek == gameweek and row.target.player_id in requested
    }
    if abstained:
        raise ValueError(
            "decision values cannot neutral-fill forecast abstentions: "
            + ",".join(str(item) for item in sorted(abstained))
        )

    rows_by_player: dict[OfficialPlayerId, list] = {player_id: [] for player_id in requested}
    for row in forecast.rows:
        if row.target.gameweek == gameweek and row.target.player_id in rows_by_player:
            rows_by_player[row.target.player_id].append(row)

    values: dict[OfficialPlayerId, PlayerGameweekValue] = {}
    for player_id, rows in rows_by_player.items():
        expected = Fraction(0, 1)
        no_appearance = Fraction(1, 1)
        for row in rows:
            expected += Fraction(
                row.expected_points_numerator,
                PROBABILITY_DENOMINATOR,
            )
            p_zero = Fraction(
                row.minutes_distribution.probability_exactly(0),
                PROBABILITY_DENOMINATOR,
            )
            no_appearance *= p_zero
        appearance = Fraction(0, 1) if not rows else 1 - no_appearance
        values[player_id] = PlayerGameweekValue(
            player_id=player_id,
            expected_points=expected,
            appearance_probability=appearance,
        )
    return values


def _lineup_limits(ruleset: RuleSet) -> tuple[dict[str, int], dict[str, int]]:
    minimum_raw = ruleset.mapping("FPL-XI-POSITION-MIN-001")
    maximum_raw = ruleset.mapping("FPL-XI-POSITION-MAX-001")
    minimum = {position: int(value) for position, value in minimum_raw.items()}
    maximum = {position: int(value) for position, value in maximum_raw.items()}
    return minimum, maximum


def _legal_lineups(
    squad: tuple[CandidatePlayer, ...],
    *,
    ruleset: RuleSet,
):
    minimum, maximum = _lineup_limits(ruleset)
    by_position = {
        position: tuple(
            sorted(row.player_id for row in squad if row.position == position)
        )
        for position in ("GK", "DEF", "MID", "FWD")
    }
    xi_size = ruleset.integer("FPL-XI-SIZE-001")
    for goalkeeper in by_position["GK"]:
        for defenders in range(minimum["DEF"], maximum["DEF"] + 1):
            for midfielders in range(minimum["MID"], maximum["MID"] + 1):
                forwards = xi_size - 1 - defenders - midfielders
                if not minimum["FWD"] <= forwards <= maximum["FWD"]:
                    continue
                for chosen_defenders in combinations(by_position["DEF"], defenders):
                    for chosen_midfielders in combinations(by_position["MID"], midfielders):
                        for chosen_forwards in combinations(by_position["FWD"], forwards):
                            yield tuple(
                                sorted(
                                    (
                                        goalkeeper,
                                        *chosen_defenders,
                                        *chosen_midfielders,
                                        *chosen_forwards,
                                    )
                                )
                            )


def _legal_outfield_counts(counts: dict[str, int], *, ruleset: RuleSet) -> bool:
    minimum, maximum = _lineup_limits(ruleset)
    return all(
        minimum[position] <= counts.get(position, 0) <= maximum[position]
        for position in ("DEF", "MID", "FWD")
    )


def _bench_state_probability(
    bits: tuple[int, ...],
    probabilities: tuple[Fraction, ...],
) -> Fraction:
    probability = Fraction(1, 1)
    for bit, appears in zip(bits, probabilities, strict=True):
        probability *= appears if bit else 1 - appears
    return probability


def _autosub_weights(
    *,
    xi_ids: tuple[OfficialPlayerId, ...],
    squad_ids: tuple[OfficialPlayerId, ...],
    positions: dict[OfficialPlayerId, str],
    appearance: dict[OfficialPlayerId, Fraction],
    outfield_order: tuple[OfficialPlayerId, ...],
    ruleset: RuleSet,
) -> dict[OfficialPlayerId, Fraction]:
    bench_ids = tuple(sorted(set(squad_ids) - set(xi_ids)))
    starting_gk = [pid for pid in xi_ids if positions[pid] == "GK"]
    bench_gk = [pid for pid in bench_ids if positions[pid] == "GK"]
    if len(starting_gk) != 1 or len(bench_gk) != 1:
        raise ValueError("legal FPL submission requires one starting and one bench goalkeeper")
    gk_start, gk_bench = starting_gk[0], bench_gk[0]
    weights: dict[OfficialPlayerId, Fraction] = {
        gk_bench: 1 - appearance[gk_start]
    }

    starters = [pid for pid in xi_ids if positions[pid] != "GK"]
    bench_out = [pid for pid in bench_ids if positions[pid] != "GK"]
    if len(outfield_order) != 3 or set(outfield_order) != set(bench_out):
        raise ValueError("outfield bench order must cover exactly the three substitutes")

    position_order = ("DEF", "MID", "FWD")
    index = {position: i for i, position in enumerate(position_order)}
    missing_distribution: dict[tuple[int, int, int], Fraction] = {
        (0, 0, 0): Fraction(1, 1)
    }
    for player_id in starters:
        position_index = index[positions[player_id]]
        p_appear = appearance[player_id]
        next_distribution: dict[tuple[int, int, int], Fraction] = {}
        for counts, probability in missing_distribution.items():
            next_distribution[counts] = (
                next_distribution.get(counts, Fraction(0, 1))
                + probability * p_appear
            )
            missing = list(counts)
            missing[position_index] += 1
            key = tuple(missing)
            next_distribution[key] = (
                next_distribution.get(key, Fraction(0, 1))
                + probability * (1 - p_appear)
            )
        missing_distribution = next_distribution

    planned_counts = {
        position: sum(positions[player_id] == position for player_id in starters)
        for position in position_order
    }
    bench_probabilities = tuple(appearance[player_id] for player_id in outfield_order)
    substitution_probability = {
        player_id: Fraction(0, 1) for player_id in outfield_order
    }
    for missing_tuple, p_start in missing_distribution.items():
        if p_start == 0 or not any(missing_tuple):
            continue
        for bench_bits in product((0, 1), repeat=3):
            state_probability = p_start * _bench_state_probability(
                bench_bits,
                bench_probabilities,
            )
            if state_probability == 0:
                continue
            live_counts = dict(planned_counts)
            missing_counts = {
                position: missing_tuple[index[position]] for position in position_order
            }
            for player_id, appears in zip(outfield_order, bench_bits, strict=True):
                if not appears or not any(missing_counts.values()):
                    continue
                for missing_position in position_order:
                    if missing_counts[missing_position] <= 0:
                        continue
                    trial = dict(live_counts)
                    trial[missing_position] -= 1
                    trial[positions[player_id]] += 1
                    if not _legal_outfield_counts(trial, ruleset=ruleset):
                        continue
                    live_counts = trial
                    missing_counts[missing_position] -= 1
                    substitution_probability[player_id] += state_probability
                    break

    for player_id in outfield_order:
        p_appear = appearance[player_id]
        weights[player_id] = (
            substitution_probability[player_id] / p_appear
            if p_appear > 0
            else Fraction(0, 1)
        )
    return weights


def _best_captain_vice(
    xi_ids: tuple[OfficialPlayerId, ...],
    values: dict[OfficialPlayerId, PlayerGameweekValue],
    *,
    captain_multiplier: int,
) -> tuple[OfficialPlayerId, OfficialPlayerId, Fraction]:
    if captain_multiplier < 2:
        raise ValueError("captain multiplier must be at least two")
    best: tuple[Fraction, int, int, OfficialPlayerId, OfficialPlayerId] | None = None
    extra_copies = captain_multiplier - 1
    for captain in xi_ids:
        captain_value = values[captain]
        captain_no_show = 1 - captain_value.appearance_probability
        for vice in xi_ids:
            if vice == captain:
                continue
            bonus = extra_copies * (
                captain_value.expected_points
                + captain_no_show * values[vice].expected_points
            )
            key = (
                bonus,
                -int(captain),
                -int(vice),
                captain,
                vice,
            )
            if best is None or key[:3] > best[:3]:
                best = key
    if best is None:
        raise ValueError("captain/vice requires at least two XI players")
    return best[3], best[4], best[0]


def _captain_multiplier(chip: DecisionChip, *, ruleset: RuleSet) -> int:
    if chip is DecisionChip.TRIPLE_CAPTAIN:
        return ruleset.integer("FPL-TRIPLE-CAPTAIN-MULTIPLIER-001")
    return ruleset.integer("FPL-CAPTAIN-MULTIPLIER-001")


def optimise_squad_submission(
    squad: tuple[CandidatePlayer, ...],
    values: dict[OfficialPlayerId, PlayerGameweekValue],
    *,
    chip: DecisionChip,
    hit_points: int,
    ruleset: RuleSet,
) -> SquadSubmission:
    """Exhaustively choose legal XI, captain/vice and bench order for a fixed squad."""

    if len(squad) != 15 or len({row.player_id for row in squad}) != 15:
        raise ValueError("submission optimisation requires exactly 15 unique players")
    if set(values) != {row.player_id for row in squad}:
        missing = sorted(set(row.player_id for row in squad) - set(values))
        extra = sorted(set(values) - set(row.player_id for row in squad))
        raise ValueError(f"submission value coverage mismatch missing={missing} extra={extra}")
    positions = {row.player_id: row.position for row in squad}
    squad_ids = tuple(sorted(positions))
    appearance = {
        player_id: values[player_id].appearance_probability for player_id in squad_ids
    }
    expected = {player_id: values[player_id].expected_points for player_id in squad_ids}
    total_squad_points = sum(expected.values(), Fraction(0, 1))
    captain_multiplier = _captain_multiplier(chip, ruleset=ruleset)

    best: tuple[Fraction, tuple[int, ...], SquadSubmission] | None = None
    for xi_ids in _legal_lineups(squad, ruleset=ruleset):
        bench_ids = tuple(sorted(set(squad_ids) - set(xi_ids)))
        bench_gks = tuple(pid for pid in bench_ids if positions[pid] == "GK")
        outfield = tuple(pid for pid in bench_ids if positions[pid] != "GK")
        if len(bench_gks) != 1 or len(outfield) != 3:
            continue
        captain, vice, captain_bonus = _best_captain_vice(
            xi_ids,
            values,
            captain_multiplier=captain_multiplier,
        )
        xi_points = sum((expected[player_id] for player_id in xi_ids), Fraction(0, 1))

        if chip is DecisionChip.BENCH_BOOST:
            bench_order = tuple(sorted(outfield))
            autosub_points = Fraction(0, 1)
            points_before_hits = total_squad_points + captain_bonus
        else:
            best_bench: tuple[Fraction, tuple[int, ...]] | None = None
            for order in permutations(sorted(outfield)):
                weights = _autosub_weights(
                    xi_ids=xi_ids,
                    squad_ids=squad_ids,
                    positions=positions,
                    appearance=appearance,
                    outfield_order=order,
                    ruleset=ruleset,
                )
                autosub = sum(
                    (
                        weights[player_id] * expected[player_id]
                        for player_id in bench_ids
                    ),
                    Fraction(0, 1),
                )
                candidate = (autosub, tuple(-int(pid) for pid in order))
                if best_bench is None or candidate > (
                    best_bench[0],
                    tuple(-int(pid) for pid in best_bench[1]),
                ):
                    best_bench = (autosub, tuple(order))
            if best_bench is None:
                raise ValueError("no legal bench order found")
            autosub_points, bench_order = best_bench
            points_before_hits = xi_points + autosub_points + captain_bonus

        objective = points_before_hits - hit_points
        mechanics = DecisionMechanics(
            xi_points=_rational(xi_points),
            autosub_points=_rational(autosub_points),
            captain_bonus=_rational(captain_bonus),
            squad_points_if_bench_boost=_rational(total_squad_points),
            points_before_hits=_rational(points_before_hits),
            hit_points=hit_points,
            objective_points=_rational(objective),
        )
        submission = SquadSubmission(
            xi_ids=xi_ids,
            captain_id=captain,
            vice_captain_id=vice,
            bench_gk_id=bench_gks[0],
            outfield_bench_order=bench_order,
            mechanics=mechanics,
        )
        tie_key = (
            tuple(-int(pid) for pid in xi_ids),
            -int(captain),
            -int(vice),
            tuple(-int(pid) for pid in bench_order),
        )
        row = (objective, tie_key, submission)
        if best is None or row[0] > best[0] or (
            row[0] == best[0] and row[1] > best[1]
        ):
            best = row
    if best is None:
        raise ValueError("fixed squad has no legal RuleSet XI")
    return best[2]
