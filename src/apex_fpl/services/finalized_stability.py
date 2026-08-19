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
    """Require an otherwise-valid launch winner to survive a broader certification.

    A narrow solver flag is not proof that the decision surface has converged. The
    adversarial ban audit found cases where the narrow result claimed stability while
    a broader exact shortlist produced a better legal winner. Therefore every narrow
    result that is otherwise publishable is followed by one broader bounded solve.

    The broader result is authoritative. GW1 floor, legality, transfer-solver bounds,
    and all publication gates are unchanged; an unstable broader result still fails
    closed.
    """
    base = reconcile_finalized_stability(optimiser(*args, **kwargs))
    if not (
        base.status == "optimal"
        and base.selected is not None
        and base.selected.within_gw1_band
    ):
        return base

    base_limit = int(kwargs.get("exact_candidate_limit", 16))
    broader_limit = max(int(retry_exact_candidate_limit), base_limit + 1)
    retry_kwargs = dict(kwargs)
    retry_kwargs["exact_candidate_limit"] = broader_limit
    broader = reconcile_finalized_stability(optimiser(*args, **retry_kwargs))

    base_ids = tuple(base.selected.squad_ids) if base.selected is not None else None
    broader_ids = tuple(broader.selected.squad_ids) if broader.selected is not None else None
    changed = base_ids != broader_ids
    return replace(
        broader,
        note=(
            f"{broader.note} Mandatory production convergence certification expanded "
            f"exact_candidate_limit from {base_limit} to {broader_limit}; "
            f"winner_changed={str(changed).lower()}. The broader result is authoritative; "
            "all original GW1-floor, legality, solver-bound and promotion requirements "
            "remain fail-closed."
        ),
    )
