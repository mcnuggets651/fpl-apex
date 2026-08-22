from __future__ import annotations

from itertools import permutations

import pandas as pd


FIRST_BENCH_MIN_APPEARANCE = 0.70
FIRST_BENCH_MIN_EXPECTED_MINUTES = 30.0
PLAYABLE_BENCH_MIN_APPEARANCE = 0.60
PLAYABLE_BENCH_MIN_EXPECTED_MINUTES = 20.0
MINIMUM_PLAYABLE_OUTFIELD_BENCH = 2
CURRENT_BENCH_POLICY_COLUMN = "current_bench_resilience_required"


class BenchResilienceError(ValueError):
    """Raised when a submitted squad/XI cannot satisfy the governed bench floor."""


def _numeric(players: pd.DataFrame, column: str) -> pd.Series:
    if column not in players.columns:
        return pd.Series(0.0, index=players.index, dtype=float)
    return pd.to_numeric(players[column], errors="coerce").fillna(0.0)


def resolve_current_bench_resilience(
    players: pd.DataFrame,
    override: bool | None,
) -> bool:
    """Resolve the current-deadline policy from an explicit override or sealed marker.

    Production ``evidence_eligibility`` stamps one uniform boolean marker on the
    decision player surface. Generic/replay surfaces without that marker default to
    no live-deadline policy. Future-only contingency callers can explicitly pass
    ``False`` even when reusing a production player surface.

    A partially populated or contradictory marker is a data-contract error; it is
    never interpreted heuristically.
    """
    if override is not None:
        return bool(override)
    if CURRENT_BENCH_POLICY_COLUMN not in players.columns:
        return False
    values = players[CURRENT_BENCH_POLICY_COLUMN]
    if values.isna().any():
        raise ValueError(
            f"{CURRENT_BENCH_POLICY_COLUMN} must be populated for every decision player"
        )
    normalised = values.astype(bool)
    unique = set(normalised.tolist())
    if len(unique) != 1:
        raise ValueError(
            f"{CURRENT_BENCH_POLICY_COLUMN} must be uniform across the decision surface"
        )
    return bool(next(iter(unique)))


def playable_outfield_ids(players: pd.DataFrame) -> set[int]:
    """Players suitable for the submitted outfield bench resilience floor."""
    app = _numeric(players, "appearance_probability")
    minutes = _numeric(players, "expected_minutes")
    outfield = players["position"].astype(str).ne("GK")
    eligible = outfield & (
        app.ge(PLAYABLE_BENCH_MIN_APPEARANCE)
        | minutes.ge(PLAYABLE_BENCH_MIN_EXPECTED_MINUTES)
    )
    return set(players.loc[eligible, "player_id"].astype(int))


def credible_first_bench_ids(players: pd.DataFrame) -> set[int]:
    """Players eligible to occupy first outfield autosub for the current deadline."""
    app = _numeric(players, "appearance_probability")
    minutes = _numeric(players, "expected_minutes")
    outfield = players["position"].astype(str).ne("GK")
    eligible = outfield & (
        app.ge(FIRST_BENCH_MIN_APPEARANCE)
        | minutes.ge(FIRST_BENCH_MIN_EXPECTED_MINUTES)
    )
    return set(players.loc[eligible, "player_id"].astype(int))


def bench_resilience_ok(
    bench_outfield_ids: set[int] | tuple[int, ...] | list[int],
    *,
    playable_ids: set[int],
    first_bench_ids: set[int],
) -> bool:
    bench = {int(pid) for pid in bench_outfield_ids}
    return (
        len(bench & {int(pid) for pid in playable_ids})
        >= MINIMUM_PLAYABLE_OUTFIELD_BENCH
        and bool(bench & {int(pid) for pid in first_bench_ids})
    )


def require_bench_resilience(
    bench_outfield_ids: set[int] | tuple[int, ...] | list[int],
    *,
    playable_ids: set[int],
    first_bench_ids: set[int],
) -> None:
    bench = {int(pid) for pid in bench_outfield_ids}
    playable_count = len(bench & {int(pid) for pid in playable_ids})
    if playable_count < MINIMUM_PLAYABLE_OUTFIELD_BENCH:
        raise BenchResilienceError(
            "submitted outfield bench has only "
            f"{playable_count} playable players; minimum "
            f"{MINIMUM_PLAYABLE_OUTFIELD_BENCH}"
        )
    if not bench & {int(pid) for pid in first_bench_ids}:
        raise BenchResilienceError(
            "submitted outfield bench has no player who clears the first-autosub floor"
        )


def admissible_outfield_orders(
    bench_outfield_ids: set[int] | tuple[int, ...] | list[int],
    *,
    first_bench_ids: set[int],
) -> tuple[tuple[int, ...], ...]:
    """All legal submitted orders whose first autosub clears the governed floor."""
    outfield = tuple(sorted(int(pid) for pid in bench_outfield_ids))
    if len(outfield) != 3:
        raise ValueError("outfield bench must contain exactly three players")
    eligible = {int(pid) for pid in first_bench_ids}
    orders = tuple(
        tuple(int(pid) for pid in order)
        for order in permutations(outfield)
        if int(order[0]) in eligible
    )
    if not orders:
        raise BenchResilienceError(
            "submitted outfield bench has no admissible first-autosub order"
        )
    return orders
