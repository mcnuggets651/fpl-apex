from __future__ import annotations

import re
from dataclasses import replace


_CONVERGENCE_CERTIFICATE = re.compile(
    r"convergence was checked between rank prefixes\s+(\d+)\s+and\s+(\d+)",
    re.IGNORECASE,
)


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


def _in_solve_certificate_covers(result, required_prefix: int) -> bool:
    """Return True only for a stable result carrying the joint optimiser's breadth proof.

    The joint optimiser evaluates candidates incrementally and records the two rank
    prefixes whose winners were compared. This is stronger than blindly launching the
    whole optimiser again at a larger *input* limit: it proves the actual evaluated
    surface reached at least ``required_prefix`` while reusing the already-computed
    transfer paths.

    The certificate is deliberately fail-closed. Legacy/mocked/foreign optimisers that
    do not emit the canonical convergence statement still receive the historical
    broader second solve.
    """
    if not bool(getattr(result, "candidate_pool_stable", False)):
        return False
    selected = getattr(result, "selected", None)
    if selected is None:
        return False
    full_ids = getattr(result, "full_pool_selected_ids", None)
    if full_ids is None or tuple(full_ids) != tuple(selected.squad_ids):
        return False
    match = _CONVERGENCE_CERTIFICATE.search(str(getattr(result, "note", "")))
    if match is None:
        return False
    left, right = (int(match.group(1)), int(match.group(2)))
    return left < right and right >= int(required_prefix)


def optimise_with_bounded_stability_retry(
    optimiser,
    *args,
    retry_exact_candidate_limit: int = 24,
    **kwargs,
):
    """Certify a launch winner broadly without duplicating proven expensive work.

    Historical production always ran the complete joint launch optimiser twice: once
    at the configured exact-candidate limit and once at a broader limit. The current
    joint optimiser already performs adaptive, cached prefix convergence internally
    (normally 32->48, extending to 64 after another identity change). Re-running the
    entire function therefore repeated every expensive future-transfer MILP and caused
    deadline-day jobs to hit their 100-minute wall.

    We now accept the first result *only* when it carries the canonical in-solve
    convergence certificate, is stable, and the certified evaluated prefix is at least
    as broad as the historical retry requirement. Otherwise the historical broader
    solve still runs unchanged. This preserves the adversarial guarantee that a narrow
    winner cannot self-certify while avoiding duplicate computation when equivalent or
    stronger breadth has already been proved inside the solve.
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
    if _in_solve_certificate_covers(base, broader_limit):
        return replace(
            base,
            note=(
                f"{base.note} Mandatory production convergence certification reused "
                f"the in-solve evaluated-prefix proof covering >= {broader_limit}; "
                "no duplicate joint optimisation was required. All original GW1-floor, "
                "legality, solver-bound and promotion requirements remain fail-closed."
            ),
        )

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
