from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, permutations, product

from apex.domain.models import (
    OfficialSnapshot,
    Position,
    ProductionProjectionSurface,
    SystemDecision,
)
from apex.domain.rules import XI_MAX, XI_MIN


@dataclass(frozen=True)
class GameweekMechanics:
    xi_ids: tuple[int, ...]
    captain_id: int
    vice_captain_id: int
    bench_order: tuple[int, ...]
    submitted_ev: float
    mechanics_warning: str | None = None
    expected_xi_points: float | None = None
    expected_autosub_points: float | None = None
    expected_captain_bonus: float | None = None
    contingency_complete: bool = False


def xp_map(
    surface: ProductionProjectionSurface,
    horizon: int,
) -> dict[int, float]:
    return {
        int(row.element_id): float(row.expected_points)
        for row in surface.rows_for_horizon(horizon)
        if row.expected_points is not None
    }


def _legal_xis(squad_ids, official: OfficialSnapshot):
    players = official.player_map()
    by = {
        position: tuple(
            sorted(
                player_id
                for player_id in squad_ids
                if players[player_id].position == position
            )
        )
        for position in Position
    }
    for goalkeeper in by[Position.GK]:
        for defenders in range(XI_MIN[Position.DEF], XI_MAX[Position.DEF] + 1):
            for midfielders in range(
                XI_MIN[Position.MID],
                XI_MAX[Position.MID] + 1,
            ):
                forwards = 10 - defenders - midfielders
                if not XI_MIN[Position.FWD] <= forwards <= XI_MAX[Position.FWD]:
                    continue
                for chosen_defenders in combinations(
                    by[Position.DEF],
                    defenders,
                ):
                    for chosen_midfielders in combinations(
                        by[Position.MID],
                        midfielders,
                    ):
                        for chosen_forwards in combinations(
                            by[Position.FWD],
                            forwards,
                        ):
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


def _clamp_probability(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def _state_probability(
    bits: tuple[int, ...],
    probabilities: list[float],
) -> float:
    probability = 1.0
    for bit, raw_probability in zip(bits, probabilities, strict=True):
        appearance = _clamp_probability(raw_probability)
        probability *= appearance if bit else 1.0 - appearance
    return probability


def _legal_outfield_counts(counts: dict[Position, int]) -> bool:
    return all(
        XI_MIN[position] <= int(counts.get(position, 0)) <= XI_MAX[position]
        for position in (Position.DEF, Position.MID, Position.FWD)
    )


def _best_captain_vice(
    xi_ids: tuple[int, ...],
    xp: dict[int, float],
    appearance: dict[int, float],
) -> tuple[int, int, float]:
    """Return expected extra captain value under the FPL vice fallback rule.

    Provider xP is unconditional, so it already contains the vice player's own
    probability of appearing. Under the marginal independent-appearance model,
    the extra captain copy for pair ``(captain, vice)`` is therefore
    ``xP(captain) + P(captain no-show) * xP(vice)``.
    """
    best: tuple[float, int, int] | None = None
    for captain in sorted(xi_ids):
        captain_probability = _clamp_probability(appearance[captain])
        for vice in sorted(xi_ids):
            if vice == captain:
                continue
            bonus = max(float(xp[captain]), 0.0) + (
                1.0 - captain_probability
            ) * max(float(xp[vice]), 0.0)
            row = (float(bonus), int(captain), int(vice))
            if (
                best is None
                or row[0] > best[0] + 1e-12
                or (
                    abs(row[0] - best[0]) <= 1e-12
                    and row[1:] < best[1:]
                )
            ):
                best = row
    if best is None:
        raise ValueError("captain/vice optimisation requires two XI players")
    return best[1], best[2], best[0]


def _autosub_weights(
    xi_ids: tuple[int, ...],
    bench_ids: tuple[int, ...],
    positions: dict[int, Position],
    appearance: dict[int, float],
    *,
    outfield_order: tuple[int, ...],
) -> dict[int, float]:
    """Return conditional-use weights for exact FPL automatic substitutions.

    Missing starting outfielders are aggregated by position. The three outfield
    bench appearance states are then enumerated in submitted priority order. This
    is equivalent to full player-state enumeration for independent appearance
    marginals while preserving FPL's legal formation constraints.
    """
    starting_goalkeepers = [
        player_id
        for player_id in xi_ids
        if positions[player_id] == Position.GK
    ]
    bench_goalkeepers = [
        player_id
        for player_id in bench_ids
        if positions[player_id] == Position.GK
    ]
    if len(starting_goalkeepers) != 1 or len(bench_goalkeepers) != 1:
        raise ValueError(
            "a legal FPL squad requires one starting and one bench goalkeeper"
        )

    starting_goalkeeper = starting_goalkeepers[0]
    bench_goalkeeper = bench_goalkeepers[0]
    weights: dict[int, float] = {
        int(bench_goalkeeper): 1.0
        - _clamp_probability(appearance[starting_goalkeeper])
    }

    starters = tuple(
        player_id
        for player_id in xi_ids
        if positions[player_id] != Position.GK
    )
    bench_outfield = tuple(
        player_id
        for player_id in bench_ids
        if positions[player_id] != Position.GK
    )
    if len(outfield_order) != 3 or set(outfield_order) != set(bench_outfield):
        raise ValueError(
            "outfield_order must contain the three outfield bench players exactly once"
        )

    position_order = (Position.DEF, Position.MID, Position.FWD)
    position_index = {
        position: index
        for index, position in enumerate(position_order)
    }

    missing_distribution: dict[tuple[int, int, int], float] = {
        (0, 0, 0): 1.0
    }
    for player_id in starters:
        index = position_index[positions[player_id]]
        appears = _clamp_probability(appearance[player_id])
        next_distribution: dict[tuple[int, int, int], float] = {}
        for missing_counts, state_probability in missing_distribution.items():
            next_distribution[missing_counts] = (
                next_distribution.get(missing_counts, 0.0)
                + state_probability * appears
            )
            missing = list(missing_counts)
            missing[index] += 1
            key = tuple(missing)
            next_distribution[key] = (
                next_distribution.get(key, 0.0)
                + state_probability * (1.0 - appears)
            )
        missing_distribution = next_distribution

    submitted_counts = {
        position: sum(
            positions[player_id] == position
            for player_id in starters
        )
        for position in position_order
    }
    bench_probabilities = [
        _clamp_probability(appearance[player_id])
        for player_id in outfield_order
    ]
    substitution_probabilities = {
        int(player_id): 0.0
        for player_id in outfield_order
    }

    for missing_tuple, starter_state_probability in missing_distribution.items():
        if starter_state_probability <= 1e-15 or not any(missing_tuple):
            continue
        for bench_bits in product((0, 1), repeat=3):
            state_probability = starter_state_probability * _state_probability(
                bench_bits,
                bench_probabilities,
            )
            if state_probability <= 1e-15:
                continue

            live_counts = dict(submitted_counts)
            missing_counts = {
                position: int(missing_tuple[index])
                for index, position in enumerate(position_order)
            }
            for player_id, appears in zip(
                outfield_order,
                bench_bits,
                strict=True,
            ):
                if not appears or not any(missing_counts.values()):
                    continue
                for missing_position in position_order:
                    if missing_counts[missing_position] <= 0:
                        continue
                    trial = dict(live_counts)
                    trial[missing_position] -= 1
                    trial[positions[player_id]] += 1
                    if not _legal_outfield_counts(trial):
                        continue
                    live_counts = trial
                    missing_counts[missing_position] -= 1
                    substitution_probabilities[int(player_id)] += state_probability
                    break

    for player_id, substitution_probability in substitution_probabilities.items():
        player_appearance = _clamp_probability(appearance[player_id])
        weights[player_id] = (
            substitution_probability / player_appearance
            if player_appearance > 1e-12
            else 0.0
        )
    return weights


def _expected_autosub_points(
    xi_ids: tuple[int, ...],
    bench_ids: tuple[int, ...],
    positions: dict[int, Position],
    xp: dict[int, float],
    appearance: dict[int, float],
    *,
    outfield_order: tuple[int, ...],
) -> float:
    weights = _autosub_weights(
        xi_ids,
        bench_ids,
        positions,
        appearance,
        outfield_order=outfield_order,
    )
    return float(
        sum(
            weight * max(float(xp.get(player_id, 0.0)), 0.0)
            for player_id, weight in weights.items()
        )
    )


def _complete_appearance_inputs(
    ids: tuple[int, ...],
    surface: ProductionProjectionSurface,
    *,
    horizon: int,
    forced_absent: frozenset[int],
) -> tuple[bool, dict[int, float]]:
    rows = {
        int(row.element_id): row
        for row in surface.rows_for_horizon(horizon)
    }
    appearance: dict[int, float] = {}
    for player_id in ids:
        if player_id in forced_absent:
            appearance[player_id] = 0.0
            continue
        row = rows.get(player_id)
        if row is None or row.p_appearance is None:
            return False, {}
        appearance[player_id] = _clamp_probability(row.p_appearance)
    return True, appearance


def _fallback_fixed_squad_mechanics(
    official: OfficialSnapshot,
    surface: ProductionProjectionSurface,
    ids: tuple[int, ...],
    *,
    horizon: int,
    xi_excluded: frozenset[int],
) -> GameweekMechanics:
    """Keep synthetic/incomplete fixtures diagnosable without claiming exact EV.

    Production certification separately fails closed when H1 contingency inputs
    are incomplete.
    """
    xp = xp_map(surface, horizon)
    players = official.player_map()
    best = None
    for xi in _legal_xis(ids, official):
        if set(xi) & set(xi_excluded):
            continue
        if any(player_id not in xp for player_id in xi):
            continue
        ranked = sorted(xi, key=lambda player_id: (-xp[player_id], player_id))
        captain = ranked[0]
        vice = ranked[1]
        submitted = sum(xp[player_id] for player_id in xi) + xp[captain]
        tie = (tuple(ranked), captain, vice)
        if (
            best is None
            or submitted > best[0] + 1e-12
            or (
                abs(submitted - best[0]) <= 1e-12
                and tie < best[1]
            )
        ):
            best = (submitted, tie, xi, captain, vice)
    if best is None:
        raise ValueError(
            "fixed squad has no legal XI with complete serving forecast"
        )

    _, _, xi, captain, vice = best
    bench = set(ids) - set(xi)
    bench_goalkeeper = next(
        player_id
        for player_id in bench
        if players[player_id].position == Position.GK
    )
    outfield = sorted(
        (
            player_id
            for player_id in bench
            if player_id != bench_goalkeeper
        ),
        key=lambda player_id: (
            -xp.get(player_id, float("-inf")),
            player_id,
        ),
    )
    warning = (
        "serving provider lacks complete appearance probabilities; "
        "submitted EV excludes contingent autosub and vice fallback value"
    )
    return GameweekMechanics(
        tuple(xi),
        int(captain),
        int(vice),
        (int(bench_goalkeeper), *tuple(int(pid) for pid in outfield)),
        float(best[0]),
        warning,
        float(sum(xp[player_id] for player_id in xi)),
        0.0,
        float(xp[captain]),
        False,
    )


def best_fixed_squad_mechanics(
    official: OfficialSnapshot,
    surface: ProductionProjectionSurface,
    squad_ids,
    *,
    horizon: int = 1,
    xi_excluded: frozenset[int] = frozenset(),
) -> GameweekMechanics:
    """Exhaustively choose XI, captain/vice and bench order for a fixed squad."""
    ids = tuple(sorted(map(int, squad_ids)))
    xp = xp_map(surface, horizon)
    players = official.player_map()
    complete, appearance = _complete_appearance_inputs(
        ids,
        surface,
        horizon=horizon,
        forced_absent=xi_excluded,
    )
    if not complete or any(player_id not in xp for player_id in ids):
        return _fallback_fixed_squad_mechanics(
            official,
            surface,
            ids,
            horizon=horizon,
            xi_excluded=xi_excluded,
        )

    positions = {
        player_id: players[player_id].position
        for player_id in ids
    }
    best = None

    for xi in _legal_xis(ids, official):
        if set(xi) & set(xi_excluded):
            continue

        bench_ids = tuple(sorted(set(ids) - set(xi)))
        bench_goalkeepers = tuple(
            player_id
            for player_id in bench_ids
            if positions[player_id] == Position.GK
        )
        outfield = tuple(
            player_id
            for player_id in bench_ids
            if positions[player_id] != Position.GK
        )
        if len(bench_goalkeepers) != 1 or len(outfield) != 3:
            continue

        captain, vice, captain_bonus = _best_captain_vice(
            tuple(xi),
            xp,
            appearance,
        )
        best_order: tuple[int, ...] | None = None
        best_autosub = -1.0
        for order in permutations(sorted(outfield)):
            autosub = _expected_autosub_points(
                tuple(xi),
                bench_ids,
                positions,
                xp,
                appearance,
                outfield_order=tuple(int(player_id) for player_id in order),
            )
            if (
                autosub > best_autosub + 1e-12
                or (
                    abs(autosub - best_autosub) <= 1e-12
                    and (
                        best_order is None
                        or tuple(order) < best_order
                    )
                )
            ):
                best_autosub = float(autosub)
                best_order = tuple(int(player_id) for player_id in order)
        assert best_order is not None

        xi_points = float(sum(max(xp[player_id], 0.0) for player_id in xi))
        total = xi_points + best_autosub + captain_bonus
        bench_order = (
            int(bench_goalkeepers[0]),
            *best_order,
        )
        tie = (
            tuple(int(player_id) for player_id in xi),
            int(captain),
            int(vice),
            bench_order,
        )
        row = (
            float(total),
            tie,
            tuple(int(player_id) for player_id in xi),
            int(captain),
            int(vice),
            bench_order,
            xi_points,
            float(best_autosub),
            float(captain_bonus),
        )
        if (
            best is None
            or row[0] > best[0] + 1e-12
            or (
                abs(row[0] - best[0]) <= 1e-12
                and row[1] < best[1]
            )
        ):
            best = row

    if best is None:
        raise ValueError(
            "fixed squad has no legal XI with complete contingency inputs"
        )

    (
        total,
        _tie,
        xi,
        captain,
        vice,
        bench_order,
        xi_points,
        autosub_points,
        captain_bonus,
    ) = best
    return GameweekMechanics(
        xi,
        captain,
        vice,
        bench_order,
        total,
        None,
        xi_points,
        autosub_points,
        captain_bonus,
        True,
    )


def decision_from_fixed_squad(
    official,
    surface,
    squad_ids,
    *,
    horizon=1,
    transfers_in=(),
    transfers_out=(),
    transfer_hits=0,
    decision_mode="HOLD",
    xi_excluded: frozenset[int] = frozenset(),
) -> SystemDecision:
    mechanics = best_fixed_squad_mechanics(
        official,
        surface,
        squad_ids,
        horizon=horizon,
        xi_excluded=xi_excluded,
    )
    return SystemDecision(
        1,
        tuple(sorted(squad_ids)),
        mechanics.xi_ids,
        mechanics.captain_id,
        mechanics.vice_captain_id,
        mechanics.bench_order,
        tuple(sorted(transfers_in)),
        tuple(sorted(transfers_out)),
        mechanics.submitted_ev,
        horizon,
        int(transfer_hits),
        decision_mode,
    )
