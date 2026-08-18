from __future__ import annotations

from dataclasses import replace


def reconcile_finalized_stability(result):
    """Correct only a stale pre-rebase stability flag with identical final IDs.

    The adaptive launch gate remains fail-closed unless both finalized prefix winners
    exist and identify exactly the same 15-player squad. No objective tolerance,
    candidate-pool size, solver limit or selection rule is altered.
    """
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
    """Retry a genuinely unstable adaptive launch on a broader bounded pool.

    Production normally evaluates the rank-prefix convergence surface generated from
    ``exact_candidate_limit=16``. A live audit showed a real 48->64 winner identity
    change, so stopping there correctly failed closed but left no path to prove later
    convergence. If (and only if) that first finalized result is otherwise optimal,
    has a selected in-band squad, and remains genuinely unstable after reconciliation,
    run one broader bounded solve. With the production retry limit of 24 the core
    optimiser checks broader 48->72->96 prefixes. The same GW1 floor, transfer solver
    policy and promotion gate remain unchanged; an unstable retry still fails closed.
    """
    result = reconcile_finalized_stability(optimiser(*args, **kwargs))
    if not (
        result.status == "optimal"
        and result.selected is not None
        and result.selected.within_gw1_band
        and result.candidate_pool_stable is False
    ):
        return result

    base_limit = int(kwargs.get("exact_candidate_limit", 16))
    broader_limit = max(int(retry_exact_candidate_limit), base_limit + 1)
    retry_kwargs = dict(kwargs)
    retry_kwargs["exact_candidate_limit"] = broader_limit
    retried = reconcile_finalized_stability(optimiser(*args, **retry_kwargs))
    return replace(
        retried,
        note=(
            f"{retried.note} Production convergence retry expanded exact_candidate_limit "
            f"from {base_limit} to {broader_limit}; all original GW1-floor, legality, "
            "solver-bound and promotion requirements remained fail-closed."
        ),
    )
