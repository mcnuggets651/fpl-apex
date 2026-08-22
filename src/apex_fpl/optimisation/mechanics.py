from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations, product

import pandas as pd

from apex_fpl.constants import XI_MAX, XI_MIN
from apex_fpl.optimisation.bench_policy import (
    admissible_outfield_orders,
    credible_first_bench_ids,
    playable_outfield_ids,
    require_bench_resilience,
    resolve_current_bench_resilience,
)


@dataclass(frozen=True)
class GameweekMechanics:
    expected_xi_points: float
    expected_autosub_points: float
    expected_captain_bonus: float
    expected_total_points: float
    captain_id: int
    vice_captain_id: int
    bench_gk_id: int
    outfield_bench_order: tuple[int, ...]

    def to_dict(self) -> dict:
        return {
            "expected_xi_points": self.expected_xi_points,
            "expected_autosub_points": self.expected_autosub_points,
            "expected_captain_bonus": self.expected_captain_bonus,
            "expected_total_points": self.expected_total_points,
            "captain_id": self.captain_id,
            "vice_captain_id": self.vice_captain_id,
            "bench_gk_id": self.bench_gk_id,
            "outfield_bench_order": list(self.outfield_bench_order),
        }


def _probability(bits: tuple[int, ...], probs: list[float]) -> float:
    out = 1.0
    for bit, p in zip(bits, probs):
        p = min(max(float(p), 0.0), 1.0)
        out *= p if bit else 1.0 - p
    return out


def _legal_counts(counts: dict[str, int]) -> bool:
    return all(
        XI_MIN[pos] <= int(counts.get(pos, 0)) <= XI_MAX[pos]
        for pos in ("DEF", "MID", "FWD")
    )


def _can_replace_slot(
    slot_positions: list[str],
    missing_slots: set[int],
    bench_position: str,
) -> int | None:
    for slot in sorted(missing_slots):
        trial = list(slot_positions)
        trial[slot] = bench_position
        counts = {pos: trial.count(pos) for pos in ("DEF", "MID", "FWD")}
        if _legal_counts(counts):
            return slot
    return None


def best_captain_vice(
    xi: pd.DataFrame,
    xp: dict[int, float],
    appearance: dict[int, float],
    *,
    captain_multiplier: int = 2,
    captain_eligible: set[int] | None = None,
) -> tuple[int, int, float]:
    ids = sorted(
        int(x) for x in pd.to_numeric(xi["player_id"], errors="coerce").dropna()
    )
    return best_captain_vice_ids(
        ids,
        xp,
        appearance,
        captain_multiplier=captain_multiplier,
        captain_eligible=captain_eligible,
    )


def best_captain_vice_ids(
    ids: list[int] | tuple[int, ...],
    xp: dict[int, float],
    appearance: dict[int, float],
    *,
    captain_multiplier: int = 2,
    captain_eligible: set[int] | None = None,
) -> tuple[int, int, float]:
    ids = sorted(int(pid) for pid in ids)
    if captain_eligible is not None:
        eligible = {int(pid) for pid in captain_eligible}
        ids = [pid for pid in ids if pid in eligible]
    if len(ids) < 2:
        raise ValueError(
            "captain/vice optimisation requires at least two eligible XI players"
        )
    copies = max(int(captain_multiplier) - 1, 1)
    best: tuple[int, int, float] | None = None
    for captain in ids:
        p_c = min(max(float(appearance.get(captain, 1.0)), 0.0), 1.0)
        for vice in ids:
            if vice == captain:
                continue
            bonus = copies * (
                max(float(xp.get(captain, 0.0)), 0.0)
                + (1.0 - p_c) * max(float(xp.get(vice, 0.0)), 0.0)
            )
            if best is None or bonus > best[2] + 1e-12:
                best = (captain, vice, bonus)
    assert best is not None
    return best


def autosub_weights_ids(
    xi_ids: tuple[int, ...],
    bench_ids: tuple[int, ...],
    positions: dict[int, str],
    appearance: dict[int, float],
    *,
    outfield_order: tuple[int, ...],
) -> dict[int, float]:
    starting_gk = [pid for pid in xi_ids if positions[pid] == "GK"]
    bench_gk = [pid for pid in bench_ids if positions[pid] == "GK"]
    if len(starting_gk) != 1 or len(bench_gk) != 1:
        raise ValueError("a legal FPL squad requires one starting and one bench goalkeeper")
    gk_start, gk_bench = starting_gk[0], bench_gk[0]
    weights = {int(gk_bench): 1.0 - float(appearance.get(gk_start, 1.0))}

    starters = [pid for pid in xi_ids if positions[pid] != "GK"]
    bench_out = [pid for pid in bench_ids if positions[pid] != "GK"]
    if set(bench_out) != set(outfield_order) or len(outfield_order) != 3:
        raise ValueError(
            "outfield_order must contain the three outfield bench players exactly once"
        )

    position_order = ("DEF", "MID", "FWD")
    position_index = {position: idx for idx, position in enumerate(position_order)}
    missing_distribution: dict[tuple[int, int, int], float] = {(0, 0, 0): 1.0}
    for pid in starters:
        idx = position_index[positions[pid]]
        appears = min(max(float(appearance.get(pid, 1.0)), 0.0), 1.0)
        next_distribution: dict[tuple[int, int, int], float] = {}
        for counts, probability in missing_distribution.items():
            next_distribution[counts] = (
                next_distribution.get(counts, 0.0) + probability * appears
            )
            missing = list(counts)
            missing[idx] += 1
            key = tuple(missing)
            next_distribution[key] = (
                next_distribution.get(key, 0.0) + probability * (1.0 - appears)
            )
        missing_distribution = next_distribution

    planned_counts = {
        position: sum(positions[pid] == position for pid in starters)
        for position in position_order
    }
    bench_probs = [float(appearance.get(pid, 1.0)) for pid in outfield_order]
    substitution_probabilities = {int(pid): 0.0 for pid in outfield_order}
    for missing_tuple, p_start in missing_distribution.items():
        if p_start <= 1e-15 or not any(missing_tuple):
            continue
        for bench_bits in product((0, 1), repeat=3):
            state_prob = p_start * _probability(bench_bits, bench_probs)
            if state_prob <= 1e-15:
                continue
            live_counts = dict(planned_counts)
            missing_counts = {
                position: int(missing_tuple[idx])
                for idx, position in enumerate(position_order)
            }
            for pid, appears in zip(outfield_order, bench_bits):
                if not appears or not any(missing_counts.values()):
                    continue
                for missing_position in position_order:
                    if missing_counts[missing_position] <= 0:
                        continue
                    trial = dict(live_counts)
                    trial[missing_position] -= 1
                    trial[positions[pid]] += 1
                    if not _legal_counts(trial):
                        continue
                    live_counts = trial
                    missing_counts[missing_position] -= 1
                    substitution_probabilities[int(pid)] += state_prob
                    break
    for pid, probability in substitution_probabilities.items():
        appears = float(appearance.get(pid, 0.0))
        weights[pid] = probability / appears if appears > 1e-12 else 0.0
    return weights


def _expected_autosub_ids(
    xi_ids: tuple[int, ...],
    bench_ids: tuple[int, ...],
    positions: dict[int, str],
    xp: dict[int, float],
    appearance: dict[int, float],
    *,
    outfield_order: tuple[int, ...],
) -> float:
    weights = autosub_weights_ids(
        xi_ids,
        bench_ids,
        positions,
        appearance,
        outfield_order=outfield_order,
    )
    return float(
        sum(weight * max(float(xp.get(pid, 0.0)), 0.0) for pid, weight in weights.items())
    )


def expected_autosub_points(
    xi: pd.DataFrame,
    bench: pd.DataFrame,
    xp: dict[int, float],
    appearance: dict[int, float],
    *,
    outfield_order: tuple[int, ...],
) -> float:
    positions = {
        int(row.player_id): str(row.position)
        for row in pd.concat([xi, bench], ignore_index=True).itertuples(index=False)
    }
    xi_ids = tuple(sorted(int(pid) for pid in xi["player_id"]))
    bench_ids = tuple(sorted(int(pid) for pid in bench["player_id"]))
    return _expected_autosub_ids(
        xi_ids,
        bench_ids,
        positions,
        xp,
        appearance,
        outfield_order=outfield_order,
    )


def evaluate_gameweek_mechanics_ids(
    squad_ids: tuple[int, ...],
    xi_ids: tuple[int, ...],
    positions: dict[int, str],
    xp: dict[int, float],
    appearance: dict[int, float],
    *,
    captain_multiplier: int = 2,
    captain_eligible: set[int] | None = None,
    playable_bench_ids: set[int] | None = None,
    first_bench_eligible_ids: set[int] | None = None,
) -> GameweekMechanics:
    if (playable_bench_ids is None) != (first_bench_eligible_ids is None):
        raise ValueError(
            "playable_bench_ids and first_bench_eligible_ids must be supplied together"
        )

    squad_set, xi_set = set(squad_ids), set(xi_ids)
    if len(squad_set) != 15 or len(xi_set) != 11 or not xi_set.issubset(squad_set):
        raise ValueError(
            "mechanics optimisation requires a legal 15-player squad and 11-player XI"
        )
    bench_ids = tuple(sorted(squad_set - xi_set))
    outfield = tuple(pid for pid in bench_ids if positions[pid] != "GK")
    bench_gk = tuple(pid for pid in bench_ids if positions[pid] == "GK")
    if len(outfield) != 3 or len(bench_gk) != 1:
        raise ValueError("bench must contain one goalkeeper and three outfield players")

    if playable_bench_ids is not None and first_bench_eligible_ids is not None:
        require_bench_resilience(
            outfield,
            playable_ids=playable_bench_ids,
            first_bench_ids=first_bench_eligible_ids,
        )
        orders = admissible_outfield_orders(
            outfield,
            first_bench_ids=first_bench_eligible_ids,
        )
    else:
        orders = tuple(
            tuple(int(pid) for pid in order)
            for order in permutations(sorted(outfield))
        )

    best_order: tuple[int, ...] | None = None
    best_autosub = -1.0
    for order in orders:
        value = _expected_autosub_ids(
            tuple(sorted(xi_set)),
            bench_ids,
            positions,
            xp,
            appearance,
            outfield_order=order,
        )
        if value > best_autosub + 1e-12 or (
            abs(value - best_autosub) <= 1e-12
            and (best_order is None or order < best_order)
        ):
            best_autosub = value
            best_order = order
    assert best_order is not None

    captain, vice, captain_bonus = best_captain_vice_ids(
        tuple(sorted(xi_set)),
        xp,
        appearance,
        captain_multiplier=captain_multiplier,
        captain_eligible=captain_eligible,
    )
    xi_points = sum(max(float(xp.get(pid, 0.0)), 0.0) for pid in xi_set)
    return GameweekMechanics(
        expected_xi_points=float(xi_points),
        expected_autosub_points=float(best_autosub),
        expected_captain_bonus=float(captain_bonus),
        expected_total_points=float(xi_points + best_autosub + captain_bonus),
        captain_id=int(captain),
        vice_captain_id=int(vice),
        bench_gk_id=int(bench_gk[0]),
        outfield_bench_order=best_order,
    )


def optimise_gameweek_mechanics(
    squad: pd.DataFrame,
    xi: pd.DataFrame,
    xp: dict[int, float],
    appearance: dict[int, float],
    *,
    captain_multiplier: int = 2,
    captain_eligible: set[int] | None = None,
    enforce_current_bench_resilience: bool | None = None,
) -> GameweekMechanics:
    """Optimise exact current Gameweek mechanics for a fixed legal XI/squad."""
    enforce = resolve_current_bench_resilience(
        squad,
        enforce_current_bench_resilience,
    )
    squad_ids = tuple(
        sorted(pd.to_numeric(squad["player_id"], errors="coerce").dropna().astype(int))
    )
    xi_ids = tuple(
        sorted(pd.to_numeric(xi["player_id"], errors="coerce").dropna().astype(int))
    )
    positions = {
        int(row.player_id): str(row.position)
        for row in squad[["player_id", "position"]].itertuples(index=False)
    }
    playable = playable_outfield_ids(squad) if enforce else None
    first = credible_first_bench_ids(squad) if enforce else None
    return evaluate_gameweek_mechanics_ids(
        squad_ids,
        xi_ids,
        positions,
        xp,
        appearance,
        captain_multiplier=captain_multiplier,
        captain_eligible=captain_eligible,
        playable_bench_ids=playable,
        first_bench_eligible_ids=first,
    )
