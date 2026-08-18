#!/usr/bin/env python3
"""Run final promotion with stability evaluated on the finalized GW1 band.

The joint-path optimiser evaluates convergence while the candidate pool is being
expanded, then rebases every candidate against the final GW1 objective before
publication. A live audit exposed a bookkeeping contradiction where the rebased
small/full prefix winners were identical but the pre-rebase stability boolean
remained false. This wrapper corrects only that exact finalized-identity case.
"""
from __future__ import annotations

import runpy

import apex_fpl.services.joint_initial_path as joint
from apex_fpl.services.finalized_stability import reconcile_finalized_stability


def main() -> None:
    original = joint.optimise_joint_initial_path

    def corrected(*args, **kwargs):
        return reconcile_finalized_stability(original(*args, **kwargs))

    joint.optimise_joint_initial_path = corrected
    runpy.run_path("scripts/apply_joint_path_promotion.py", run_name="__main__")


if __name__ == "__main__":
    main()
