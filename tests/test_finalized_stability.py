from __future__ import annotations

from dataclasses import dataclass

from apex_fpl.services.finalized_stability import (
    optimise_with_bounded_stability_retry,
    reconcile_finalized_stability,
)


@dataclass(frozen=True)
class _Selected:
    within_gw1_band: bool = True
    squad_ids: tuple[int, ...] = tuple(range(1, 16))


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


def test_missing_in_solve_certificate_falls_back_to_broader_solve() -> None:
    calls: list[int] = []
    result = _Result()

    def optimiser(*args, **kwargs):
        calls.append(int(kwargs.get("exact_candidate_limit", 16)))
        return result

    returned = optimise_with_bounded_stability_retry(
        optimiser,
        exact_candidate_limit=16,
        retry_exact_candidate_limit=24,
    )

    assert calls == [16, 24]
    assert returned.candidate_pool_stable is False


def test_canonical_in_solve_certificate_avoids_duplicate_expensive_solve() -> None:
    calls: list[int] = []
    stable_ids = tuple(range(101, 116))
    stable = _Result(
        selected=_Selected(squad_ids=stable_ids),
        candidate_pool_stable=True,
        small_pool_selected_ids=stable_ids,
        full_pool_selected_ids=stable_ids,
        note="Candidate convergence was checked between rank prefixes 32 and 48; rank 64 is conditional.",
    )

    def optimiser(*args, **kwargs):
        calls.append(int(kwargs.get("exact_candidate_limit", 16)))
        return stable

    returned = optimise_with_bounded_stability_retry(
        optimiser,
        exact_candidate_limit=16,
        retry_exact_candidate_limit=24,
    )
    assert calls == [16]
    assert returned.candidate_pool_stable is True
    assert returned.selected == stable.selected
    assert "no duplicate joint optimisation" in returned.note


def test_certificate_must_cover_historical_broader_requirement() -> None:
    calls: list[int] = []
    ids = tuple(range(101, 116))

    def optimiser(*args, **kwargs):
        limit = int(kwargs.get("exact_candidate_limit", 16))
        calls.append(limit)
        return _Result(
            selected=_Selected(squad_ids=ids),
            candidate_pool_stable=True,
            small_pool_selected_ids=ids,
            full_pool_selected_ids=ids,
            note="Candidate convergence was checked between rank prefixes 16 and 20.",
        )

    optimise_with_bounded_stability_retry(
        optimiser,
        exact_candidate_limit=16,
        retry_exact_candidate_limit=24,
    )
    assert calls == [16, 24]


def test_certificate_requires_full_prefix_winner_to_match_selected() -> None:
    calls: list[int] = []
    selected_ids = tuple(range(101, 116))
    other_ids = tuple(range(201, 216))

    def optimiser(*args, **kwargs):
        calls.append(int(kwargs.get("exact_candidate_limit", 16)))
        return _Result(
            selected=_Selected(squad_ids=selected_ids),
            candidate_pool_stable=True,
            small_pool_selected_ids=selected_ids,
            full_pool_selected_ids=other_ids,
            note="Candidate convergence was checked between rank prefixes 32 and 48.",
        )

    optimise_with_bounded_stability_retry(optimiser, exact_candidate_limit=16)
    assert calls == [16, 24]


def test_reconciled_identity_without_breadth_proof_still_retries() -> None:
    calls: list[int] = []
    ids = tuple(range(1, 16))

    def optimiser(*args, **kwargs):
        calls.append(int(kwargs.get("exact_candidate_limit", 16)))
        return _Result(
            candidate_pool_stable=False,
            small_pool_selected_ids=ids,
            full_pool_selected_ids=ids,
        )

    returned = optimise_with_bounded_stability_retry(optimiser, exact_candidate_limit=16)
    assert calls == [16, 24]
    assert returned.candidate_pool_stable is True


def test_non_optimal_or_out_of_band_result_is_not_retried() -> None:
    for result in (
        _Result(status="inconclusive"),
        _Result(selected=_Selected(within_gw1_band=False)),
    ):
        calls = 0

        def optimiser(*args, _result=result, **kwargs):
            nonlocal calls
            calls += 1
            return _result

        returned = optimise_with_bounded_stability_retry(optimiser)
        assert calls == 1
        assert returned.status == result.status
