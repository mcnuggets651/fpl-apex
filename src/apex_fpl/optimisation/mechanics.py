from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations, product

import pandas as pd

from apex_fpl.constants import XI_MAX, XI_MIN


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
    # Goalkeeper substitution is handled separately. For outfield autosubs FPL's
    # formation test is 3+ DEF, 2+ MID and 1+ FWD (with the normal maxima).
    return all(
        XI_MIN[pos] <= int(counts.get(pos, 0)) <= XI_MAX[pos]
        for pos in ("DEF", "MID", "FWD")
    )


def _can_replace_slot(
    slot_positions: list[str],
    missing_slots: set[int],
    bench_position: str,
) -> int | None:
    """Return a missing XI slot that can legally be replaced by the bench player."""
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
    """Choose captain/vice using the exact FPL no-show fallback expectation.

    ``xp`` is unconditional expected FPL points, so it already includes the vice
    player's own appearance probability. The additional captain value for pair
    (c, v) is therefore

      (multiplier-1) * [xP(c) + P(c no-show) * xP(v)].
    """
    ids = [int(x) for x in pd.to_numeric(xi["player_id"], errors="coerce").dropna()]
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


def expected_autosub_points(
    xi: pd.DataFrame,
    bench: pd.DataFrame,
    xp: dict[int, float],
    appearance: dict[int, float],
    *,
    outfield_order: tuple[int, ...],
) -> float:
    """Exact expected autosub value for a submitted XI and outfield bench order.

    The calculation enumerates binary appearance states for the ten starting
    outfielders and three outfield substitutes (8,192 states). This is small enough
    to be exact and avoids the constant bench-weight approximation when the final
    recommendation is presented.
    """
    xi_rows = xi.copy()
    bench_rows = bench.copy()
    positions = {
        int(row.player_id): str(row.position)
        for row in pd.concat([xi_rows, bench_rows], ignore_index=True).itertuples(index=False)
    }

    starting_gk = [
        int(r.player_id)
        for r in xi_rows.itertuples(index=False)
        if str(r.position) == "GK"
    ]
    bench_gk = [
        int(r.player_id)
        for r in bench_rows.itertuples(index=False)
        if str(r.position) == "GK"
    ]
    if len(starting_gk) != 1 or len(bench_gk) != 1:
        raise ValueError("a legal FPL squad requires one starting and one bench goalkeeper")

    gk_start, gk_bench = starting_gk[0], bench_gk[0]
    gk_value = (1.0 - float(appearance.get(gk_start, 1.0))) * max(
        float(xp.get(gk_bench, 0.0)), 0.0
    )

    starters = [
        int(r.player_id)
        for r in xi_rows.itertuples(index=False)
        if str(r.position) != "GK"
    ]
    bench_out = [
        int(r.player_id)
        for r in bench_rows.itertuples(index=False)
        if str(r.position) != "GK"
    ]
    if set(bench_out) != set(outfield_order) or len(outfield_order) != 3:
        raise ValueError(
            "outfield_order must contain the three outfield bench players exactly once"
        )

    starter_probs = [float(appearance.get(pid, 1.0)) for pid in starters]
    bench_probs = [float(appearance.get(pid, 1.0)) for pid in outfield_order]
    conditional = {
        pid: (
            max(float(xp.get(pid, 0.0)), 0.0) / float(appearance.get(pid, 0.0))
            if float(appearance.get(pid, 0.0)) > 1e-12
            else 0.0
        )
        for pid in outfield_order
    }

    slot_positions = [positions[pid] for pid in starters]
    expected = 0.0
    for starter_bits in product((0, 1), repeat=len(starters)):
        p_start = _probability(starter_bits, starter_probs)
        if p_start <= 1e-15:
            continue
        missing = {idx for idx, bit in enumerate(starter_bits) if not bit}
        if not missing:
            continue
        for bench_bits in product((0, 1), repeat=3):
            p_bench = _probability(bench_bits, bench_probs)
            state_prob = p_start * p_bench
            if state_prob <= 1e-15:
                continue
            live_slots = list(slot_positions)
            missing_slots = set(missing)
            contribution = 0.0
            for pid, appears in zip(outfield_order, bench_bits):
                if not appears or not missing_slots:
                    continue
                slot = _can_replace_slot(live_slots, missing_slots, positions[pid])
                if slot is None:
                    continue
                live_slots[slot] = positions[pid]
                missing_slots.remove(slot)
                contribution += conditional[pid]
            expected += state_prob * contribution
    return float(gk_value + expected)


def optimise_gameweek_mechanics(
    squad: pd.DataFrame,
    xi: pd.DataFrame,
    xp: dict[int, float],
    appearance: dict[int, float],
    *,
    captain_multiplier: int = 2,
    captain_eligible: set[int] | None = None,
) -> GameweekMechanics:
    """Optimise captain/vice and bench order for a fixed legal XI/squad."""
    squad_ids = set(
        pd.to_numeric(squad["player_id"], errors="coerce").dropna().astype(int)
    )
    xi_ids = set(pd.to_numeric(xi["player_id"], errors="coerce").dropna().astype(int))
    if len(squad_ids) != 15 or len(xi_ids) != 11 or not xi_ids.issubset(squad_ids):
        raise ValueError(
            "mechanics optimisation requires a legal 15-player squad and 11-player XI"
        )

    bench = squad[~squad["player_id"].astype(int).isin(xi_ids)].copy()
    outfield = [
        int(r.player_id)
        for r in bench.itertuples(index=False)
        if str(r.position) != "GK"
    ]
    gk = [
        int(r.player_id)
        for r in bench.itertuples(index=False)
        if str(r.position) == "GK"
    ]
    if len(outfield) != 3 or len(gk) != 1:
        raise ValueError("bench must contain one goalkeeper and three outfield players")

    best_order: tuple[int, ...] | None = None
    best_autosub = -1.0
    for order in permutations(outfield):
        value = expected_autosub_points(
            xi,
            bench,
            xp,
            appearance,
            outfield_order=tuple(int(x) for x in order),
        )
        if value > best_autosub + 1e-12:
            best_autosub = value
            best_order = tuple(int(x) for x in order)
    assert best_order is not None

    captain, vice, captain_bonus = best_captain_vice(
        xi,
        xp,
        appearance,
        captain_multiplier=captain_multiplier,
        captain_eligible=captain_eligible,
    )
    xi_points = sum(max(float(xp.get(pid, 0.0)), 0.0) for pid in xi_ids)
    return GameweekMechanics(
        expected_xi_points=float(xi_points),
        expected_autosub_points=float(best_autosub),
        expected_captain_bonus=float(captain_bonus),
        expected_total_points=float(xi_points + best_autosub + captain_bonus),
        captain_id=int(captain),
        vice_captain_id=int(vice),
        bench_gk_id=int(gk[0]),
        outfield_bench_order=best_order,
    )
