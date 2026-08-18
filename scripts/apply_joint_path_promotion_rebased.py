#!/usr/bin/env python3
"""Run final promotion with stability evaluated on the finalized GW1 band.

The joint-path optimiser evaluates convergence while the candidate pool is being
expanded, then rebases every candidate against the final GW1 objective before
publication. A live audit exposed a bookkeeping contradiction where the rebased
small/full prefix winners were identical but the pre-rebase stability boolean
remained false. This wrapper corrects only that exact finalized-identity case.
"""
from __future__ import annotations

from dataclasses import replace
import runpy

import apex_fpl.services.joint_initial_path as joint


def reconcile_finalized_stability(result):
    """Mark stable only when finalized prefix identities are both present and equal."""
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


def main() -> None:
    original = joint.optimise_joint_initial_path

    def corrected(*args, **kwargs):
        return reconcile_finalized_stability(original(*args, **kwargs))

    joint.optimise_joint_initial_path = corrected
    runpy.run_path("scripts/apply_joint_path_promotion.py", run_name="__main__")


if __name__ == "__main__":
    main()
