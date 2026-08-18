#!/usr/bin/env python3
"""Run final promotion with finalized stability plus a bounded convergence retry.

The joint-path optimiser evaluates convergence while the candidate pool is being
expanded, then rebases every candidate against the final GW1 objective before
publication. First reconcile only the stale-boolean case where finalized prefix
winners are identical. If the finalized winner genuinely still changes at the
normal production boundary, run one broader bounded convergence solve; all existing
GW1-floor, legality, solver-bound and promotion gates remain unchanged and fail closed.
"""
from __future__ import annotations

import runpy

import apex_fpl.services.joint_initial_path as joint
from apex_fpl.services.finalized_stability import optimise_with_bounded_stability_retry


def main() -> None:
    original = joint.optimise_joint_initial_path

    def corrected(*args, **kwargs):
        return optimise_with_bounded_stability_retry(original, *args, **kwargs)

    joint.optimise_joint_initial_path = corrected
    runpy.run_path("scripts/apply_joint_path_promotion.py", run_name="__main__")


if __name__ == "__main__":
    main()
