# Deadline-safe canonical convergence certification

## Incident

On 21 August 2026 the canonical and adaptive production workflows repeatedly reached the final GW1 launch strategy stage after all upstream projection, bundle and independent-solver checks had passed, then exhausted the 100-minute job budget.

The expensive path was being certified twice. `optimise_joint_initial_path` already performs adaptive evaluated-prefix convergence: it evaluates an initial prefix, extends the same cached candidate set to a broader prefix, and extends again after a winner identity change. The promotion compatibility wrapper then discarded that proof and launched the complete joint optimiser again with a larger `exact_candidate_limit`. Because each launch candidate can require a multi-Gameweek transfer MILP, the second top-level invocation repeated the dominant work.

## Permanent contract

The wrapper may reuse the first solve only when all of the following are true:

1. the result is optimal and the selected squad remains inside the GW1 regret band;
2. the optimiser reports `candidate_pool_stable=true`;
3. the reported full-prefix winner is exactly the selected squad;
4. the canonical convergence note proves that two increasing evaluated rank prefixes were compared; and
5. the broader evaluated prefix is at least as large as the historical mandatory retry requirement.

If any part of that proof is absent, malformed, too narrow or inconsistent, the historical broader second solve still runs. This makes the optimisation fail closed for legacy, mocked or foreign optimisers while avoiding duplicate work for the canonical adaptive optimiser.

## Protections deliberately unchanged

This change does **not** reduce the GW horizon, projection surface, budget/club/formation legality, GW1 regret floor, transfer candidate limit, solver optimality/bound handling, exact XI/captain/vice/autosub mechanics, player evidence eligibility, football-reality gate, or final publication gate.

The adversarial invariant remains: a narrow winner cannot self-certify. The implementation changes only how an already broader, incrementally evaluated proof is reused.

## Regression coverage

Tests cover:

- legacy/no-certificate results still receiving the broader solve;
- a canonical 32→48 in-solve certificate avoiding duplicate optimisation;
- an in-solve certificate narrower than the historical requirement falling back to the broader solve;
- a mismatch between selected and full-prefix winner falling back to the broader solve;
- identity reconciliation alone being insufficient to bypass breadth certification;
- the original adversarial test where a narrow optimiser claims stability but a broader solve finds a different winner.
