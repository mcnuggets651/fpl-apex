# Executable action mechanics contract — 2026-08-22

## Purpose

Apex has two distinct optimisation responsibilities in season:

1. the transfer-path MILP chooses the legal squad transition, transfer count, hit cost, bank state and future contingencies;
2. an independent exact current-Gameweek solve chooses the submitted XI, captain, vice-captain and bench order on the resulting 15.

The second solve is the only authority for executable current-Gameweek mechanics.

## Failure that motivated this contract

A certified GW2 artifact exposed a publication ambiguity: the canonical top-level recommendation contained the independently exact-rescored captain and vice-captain, while the embedded `action_now` object still contained the transfer optimiser's provisional captain and vice-captain. The squad and XI identities matched, so existing top-level mechanics parity passed even though a consumer reading `action_now` could see a different captain.

A subsequent serialized-artifact review found a second publication omission: the in-season canonical wrapper published bench names but omitted the already-certified bench player IDs. That made the human-readable recommendation look complete while preventing an independent consumer from proving the ordered bench identities without resolving names again.

Neither condition is an acceptable user-facing contract. One actionable payload must have one authoritative, machine-verifiable set of mechanics.

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

The canonical top-level recommendation must publish both display names and immutable player IDs for all mechanics:

- `captain` + `captain_id`;
- `vice_captain` + `vice_captain_id`;
- `bench_gk` + `bench_gk_id`;
- `outfield_bench_order` + `outfield_bench_order_ids`.

For in-season publication the wrapper must independently re-resolve every bench name against the canonical 15, require name↔ID equality, and prove that `{bench_gk_id} ∪ outfield_bench_order_ids` is exactly `squad_ids − xi_ids`. The ordered outfield ID list must remain aligned position-for-position with the ordered display-name list.

The canonical top-level recommendation and `action_now` therefore describe the same executable mechanics without requiring downstream name inference.

## Fail-closed conditions

Publication must not proceed as an optimal actionable strategy if any of the following occurs:

- `action_now.squad` is not exactly 15 unique players;
- the action squad identities differ from the independently rescored canonical 15;
- the exact XI is not 11 unique players from that 15;
- exact captain or vice-captain is outside the XI or they are identical;
- exact bench identities refer to players outside the 15;
- the ordered outfield bench is not exactly three unique players;
- a canonical bench name does not resolve uniquely to its published ID;
- the four published bench identities are not exactly the complement of the canonical XI.

A reconciliation failure returns an error/unavailable strategy rather than retaining transfer-optimiser mechanics as a fallback.

## Regression coverage

`tests/test_strategy.py` verifies all of the following:

1. a normal receding-horizon solve publishes `action_now` mechanics identical to the canonical exact-rescore mechanics;
2. deliberately wrong provisional optimiser captain/vice/XI values are overwritten by the exact-rescore authority;
3. a malformed or identity-inconsistent action squad fails closed.

`tests/test_joint_path_promotion.py` additionally verifies:

1. in-season publication carries bench names and IDs together;
2. the four bench IDs are exactly the canonical `squad − XI` complement;
3. a bench name/ID disagreement fails closed;
4. a bench surface that is not the exact XI complement fails closed.

The final answer contract and release-generation certifier independently repeat the mechanics comparison after serialization. This contract is intentionally stronger than merely checking the top-level recommendation: it protects API consumers that execute `action_now` directly and prevents a green artifact from containing contradictory or identity-ambiguous executable instructions.
