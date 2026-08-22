# Executable action mechanics contract — 2026-08-22

## Purpose

Apex has two distinct optimisation responsibilities in season:

1. the transfer-path MILP chooses the legal squad transition, transfer count, hit cost, bank state and future contingencies;
2. an independent exact current-Gameweek solve chooses the submitted XI, captain, vice-captain and bench order on the resulting 15.

The second solve is the only authority for executable current-Gameweek mechanics.

## Failure that motivated this contract

A certified GW2 artifact exposed a publication ambiguity: the canonical top-level recommendation contained the independently exact-rescored captain and vice-captain, while the embedded `action_now` object still contained the transfer optimiser's provisional captain and vice-captain. The squad and XI identities matched, so existing top-level mechanics parity passed even though a consumer reading `action_now` could see a different captain.

That is not an acceptable user-facing contract. One actionable payload must have one authoritative set of mechanics.

## Required behaviour

For an optimal receding-horizon strategy, `action_now` must preserve the transfer optimiser's transition facts:

- Gameweek;
- free transfers before the action;
- transfers in and out;
- transfer count;
- hit cost;
- bank after the action;
- chip state.

Before `action_now` becomes executable, Apex must replace its provisional mechanics with the independent exact current-Gameweek rescore:

- exact 15 identity;
- exact XI;
- exact captain;
- exact vice-captain;
- exact bench goalkeeper;
- exact ordered outfield bench;
- exact expected total points.

The executable payload records:

- `mechanics_authority = independent_exact_current_gameweek_rescore`;
- `mechanics_reconciled = true`;
- `exact_expected_total_points` from the exact mechanics solve.

The canonical top-level recommendation and `action_now` therefore describe the same executable mechanics.

## Fail-closed conditions

Publication must not proceed as an optimal actionable strategy if any of the following occurs:

- `action_now.squad` is not exactly 15 unique players;
- the action squad identities differ from the independently rescored canonical 15;
- the exact XI is not 11 unique players from that 15;
- exact captain or vice-captain is outside the XI or they are identical;
- exact bench identities refer to players outside the 15;
- the ordered outfield bench is not exactly three unique players.

A reconciliation failure returns an error/unavailable strategy rather than retaining transfer-optimiser mechanics as a fallback.

## Regression coverage

`tests/test_strategy.py` now verifies all of the following:

1. a normal receding-horizon solve publishes `action_now` mechanics identical to the canonical exact-rescore mechanics;
2. deliberately wrong provisional optimiser captain/vice/XI values are overwritten by the exact-rescore authority;
3. a malformed or identity-inconsistent action squad fails closed.

This contract is intentionally stronger than merely checking the top-level recommendation. It protects API consumers that execute `action_now` directly and prevents a green artifact from containing two contradictory actionable captaincy instructions.
