from __future__ import annotations

import re
from dataclasses import replace


# The joint optimiser's certificate is primarily semantic state on the result
# (selected/full-prefix identity + stable flag). Older/current result objects encode
# the evaluated rank-prefix breadth in the human-readable note, so keep a deliberately
# narrow compatibility parser for both grammatical forms that have existed in
# production. If/when a structured convergence_rank_prefixes field is present, it is
# authoritative and malformed structured data fails closed rather than falling back
# to prose.
_LEGACY_CONVERGENCE_CERTIFICATE = re.compile(
    r"convergence\s+(?:is|was)\s+checked between rank prefixes\s+(\d+)\s+and\s+(\d+)",
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


def _exact_prefix(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    try:
        if float(value) != float(parsed):
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed >= 1 else None


def _convergence_prefixes(result) -> tuple[int, int] | None:
    """Read the evaluated-prefix breadth certificate without accepting corruption."""
    structured = getattr(result, "convergence_rank_prefixes", None)
    if structured is not None:
        if not isinstance(structured, (tuple, list)) or len(structured) != 2:
            return None
        left = _exact_prefix(structured[0])
        right = _exact_prefix(structured[1])
        if left is None or right is None:
            return None
        return left, right

    match = _LEGACY_CONVERGENCE_CERTIFICATE.search(str(getattr(result, "note", "")))
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _in_solve_certificate_covers(result, required_prefix: int) -> bool:
    """Return True only for a stable result carrying the joint optimiser's breadth proof.

    The joint optimiser evaluates candidates incrementally and records the two rank
    prefixes whose winners were compared. This is stronger than blindly launching the
    whole optimiser again at a larger *input* limit: it proves the actual evaluated
    surface reached at least ``required_prefix`` while reusing the already-computed
    transfer paths.

    The certificate is deliberately fail-closed. Legacy/mocked/foreign optimisers that
    do not emit a recognised certificate still receive the historical broader second
    solve. A structured certificate, when supplied, is authoritative; malformed
    structured data is never rescued by parsing a human-readable note.
    """
    if not bool(getattr(result, "candidate_pool_stable", False)):
        return False
    selected = getattr(result, "selected", None)
    if selected is None:
        return False
    full_ids = getattr(result, "full_pool_selected_ids", None)
    if full_ids is None or tuple(full_ids) != tuple(selected.squad_ids):
        return False
    prefixes = _convergence_prefixes(result)
    if prefixes is None:
        return False
    left, right = prefixes
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
