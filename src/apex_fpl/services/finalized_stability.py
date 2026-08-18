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
