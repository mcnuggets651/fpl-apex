from __future__ import annotations

from itertools import permutations

import pandas as pd


FIRST_BENCH_MIN_APPEARANCE = 0.70
FIRST_BENCH_MIN_EXPECTED_MINUTES = 30.0
PLAYABLE_BENCH_MIN_APPEARANCE = 0.60
PLAYABLE_BENCH_MIN_EXPECTED_MINUTES = 20.0
MINIMUM_PLAYABLE_OUTFIELD_BENCH = 2


def _numeric(players: pd.DataFrame, column: str) -> pd.Series:
    if column not in players.columns:
        return pd.Series(0.0, index=players.index, dtype=float)
    return pd.to_numeric(players[column], errors="coerce").fillna(0.0)


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
    return tuple(
        tuple(int(pid) for pid in order)
        for order in permutations(outfield)
        if int(order[0]) in eligible
    )
