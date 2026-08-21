from __future__ import annotations

from dataclasses import replace


def reconcile_finalized_stability(result):
    """Correct only a stale pre-rebase stability flag with identical final IDs."""
    small = result.small_pool_selected_ids
    full = result.full_pool_selected_ids
    if (
        result.status == "optimal"
        and result.candidate_pool_stable is False
        and small is not None
        and full is not None
        and tuple(small) == tuple(full)
    ):
        return replace(
            result,
            candidate_pool_stable=True,
            note=(
                f"{result.note} Finalized GW1-band reconciliation confirmed identical "
                "small/full prefix squad identities."
            ),
        )
    return result


def optimise_with_bounded_stability_retry(
    optimiser,
    *args,
    retry_exact_candidate_limit: int = 24,
    **kwargs,
):
    """Run one bounded launch solve and trust its in-solve convergence certificate.

    Production previously re-ran the complete joint launch optimiser with a broader
    ``exact_candidate_limit`` after the first solve had already performed adaptive
    prefix convergence. That duplicated every expensive future transfer MILP for the
    leading candidates and was the dominant deadline-day runtime failure.

    Convergence certification now belongs inside ``optimise_joint_initial_path`` so
    candidate evaluations are accumulated once and the broader prefix is evaluated
    incrementally. This wrapper is retained for compatibility with the promotion
    entry point, but it must never launch a second copy of the same optimisation.

    ``retry_exact_candidate_limit`` is intentionally retained as a no-op compatibility
    argument for callers/tests from the old contract. Legality, GW1 floor, solver
    bounds and fail-closed publication semantics remain enforced by the optimiser.
    """
    del retry_exact_candidate_limit
    return reconcile_finalized_stability(optimiser(*args, **kwargs))
