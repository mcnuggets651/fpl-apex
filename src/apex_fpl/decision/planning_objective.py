"""Exact receding-horizon objective helpers.

The chip-option policy values one unused chip entitlement. FPL 2026/27 grants two
set-specific entitlements for each long-lived chip. At a planning terminal state, the
reserve therefore sums the exact configured option value for every unused entitlement
that has not expired. Future second-set entitlements are included before GW20 because
they are guaranteed by the RuleSet; they are constant across paths until a horizon can
consume them, but keeping them explicit makes cross-half horizons reconcile correctly.
"""

from __future__ import annotations

from apex_fpl.core.decision import RationalValue
from apex_fpl.core.decision_policy_support import ChipOptionValuePolicy, ExactPolicyValue
from apex_fpl.core.planning import PlanningState
from apex_fpl.core.rules import RuleSet


_CHIPS = ("BENCH_BOOST", "FREE_HIT", "TRIPLE_CAPTAIN", "WILDCARD")


def policy_value_to_rational(value: ExactPolicyValue) -> RationalValue:
    return RationalValue(value.numerator, value.denominator)


def _add(left: RationalValue, right: RationalValue) -> RationalValue:
    return RationalValue(
        left.numerator * right.denominator + right.numerator * left.denominator,
        left.denominator * right.denominator,
    )


def _eligible_sets_at_terminal(state: PlanningState, *, ruleset: RuleSet) -> tuple[int, ...]:
    first_last = ruleset.integer("FPL-CHIP-FIRST-SET-LAST-GW-001")
    second_first = ruleset.integer("FPL-CHIP-SECOND-SET-FIRST-GW-001")
    if second_first != first_last + 1:
        raise ValueError("chip-set boundary must be contiguous for terminal reserve semantics")
    if state.gameweek <= first_last:
        return (1, 2)
    if state.gameweek >= second_first:
        return (2,)
    raise ValueError(f"terminal gameweek {state.gameweek} is outside configured chip sets")


def terminal_chip_reserve(
    state: PlanningState,
    policy: ChipOptionValuePolicy,
    *,
    ruleset: RuleSet,
) -> RationalValue:
    """Return exact option reserve for all unexpired unused chip entitlements.

    ``state.gameweek`` is the next deadline after the final scored planning step. A set-1
    entitlement therefore expires as soon as the terminal state reaches GW20. A set-2
    entitlement is already economically relevant before GW20 because the RuleSet grants
    it later in the same season. Free-Hit GW19/GW20 consecutiveness does not destroy the
    second entitlement; it only delays the first legal use to a later Gameweek.
    """

    if state.season != ruleset.season or policy.season != ruleset.season:
        raise ValueError("terminal chip reserve season mismatch")
    values = dict(policy.option_values)
    if tuple(sorted(values)) != _CHIPS:
        raise ValueError("terminal chip reserve requires values for all four chips")
    used = {(row.chip, row.set_number) for row in state.chips_used}
    reserve = RationalValue.zero()
    for set_number in _eligible_sets_at_terminal(state, ruleset=ruleset):
        for chip in _CHIPS:
            if (chip, set_number) in used:
                continue
            reserve = _add(reserve, policy_value_to_rational(values[chip]))
    return reserve
