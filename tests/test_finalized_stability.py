from __future__ import annotations

from dataclasses import dataclass

from apex_fpl.services.finalized_stability import (
    optimise_with_bounded_stability_retry,
    reconcile_finalized_stability,
)


@dataclass(frozen=True)
class _Selected:
    within_gw1_band: bool = True


@dataclass(frozen=True)
class _Result:
    status: str = "optimal"
    selected: _Selected | None = _Selected()
    candidate_pool_stable: bool = False
    small_pool_selected_ids: tuple[int, ...] | None = tuple(range(1, 16))
    full_pool_selected_ids: tuple[int, ...] | None = tuple(range(16, 31))
    note: str = "base"


def test_reconcile_only_repairs_identical_finalized_squads() -> None:
    ids = tuple(range(1, 16))
    result = _Result(small_pool_selected_ids=ids, full_pool_selected_ids=ids)
    reconciled = reconcile_finalized_stability(result)
    assert reconciled.candidate_pool_stable is True

    different = _Result(
        small_pool_selected_ids=ids,
        full_pool_selected_ids=tuple(range(2, 17)),
    )
    assert reconcile_finalized_stability(different).candidate_pool_stable is False


def test_genuine_instability_gets_one_broader_bounded_retry() -> None:
    calls: list[int] = []
    first = _Result()
    stable_ids = tuple(range(101, 116))
    second = _Result(
        candidate_pool_stable=True,
        small_pool_selected_ids=stable_ids,
        full_pool_selected_ids=stable_ids,
        note="retry",
    )

    def optimiser(*args, **kwargs):
        calls.append(int(kwargs.get("exact_candidate_limit", 16)))
        return first if len(calls) == 1 else second

    result = optimise_with_bounded_stability_retry(
        optimiser,
        exact_candidate_limit=16,
    )

    assert calls == [16, 24]
    assert result.candidate_pool_stable is True
    assert "expanded exact_candidate_limit from 16 to 24" in result.note


def test_broader_retry_remains_fail_closed_when_still_unstable() -> None:
    calls: list[int] = []

    def optimiser(*args, **kwargs):
        calls.append(int(kwargs.get("exact_candidate_limit", 16)))
        return _Result(note=f"attempt-{len(calls)}")

    result = optimise_with_bounded_stability_retry(
        optimiser,
        exact_candidate_limit=16,
    )

    assert calls == [16, 24]
    assert result.candidate_pool_stable is False


def test_non_optimal_or_out_of_band_result_does_not_retry() -> None:
    for result in (
        _Result(status="inconclusive"),
        _Result(selected=_Selected(within_gw1_band=False)),
        _Result(candidate_pool_stable=True),
    ):
        calls = 0

        def optimiser(*args, _result=result, **kwargs):
            nonlocal calls
            calls += 1
            return _result

        returned = optimise_with_bounded_stability_retry(optimiser)
        assert calls == 1
        assert returned.status == result.status
