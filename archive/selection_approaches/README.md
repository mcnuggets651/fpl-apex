# Archived Apex Selection Approaches

This directory records selection philosophies that are **not valid user-facing Apex recommendation paths**.

## Archived / superseded

### Standalone Pinnacle as the final answer
Historical role: maximum-EV team presented directly as the final Apex recommendation.

Current status: **superseded as a user-facing interface**. Maximum-EV remains the mandatory primary optimisation baseline and automatic fallback inside the unified policy, but it is now an internal decision layer rather than a separate answer.

### Standalone Elite weighted-score selection
Historical role: select the team by directly maximising the 35/20/15/10/10/5/5 Elite percentile utility.

Current status: **retired**. This could sacrifice raw expected points and compress genuine differences between premium and cheaper assets.

### Bounded ±5% Elite-adjusted xP
Historical role: multiply raw xP by a bounded Elite preference modifier.

Current status: **retired before production merge**. It still mixed forecast construction with selection preference.

### Standalone CVaR / safety team
Historical role: lower-tail/risk-adjusted candidate treated as a possible alternative recommendation.

Current status: **diagnostic only**. CVaR measures fragility/downside; it does not silently replace the maximum-points objective.

### Value / differential / ownership-led team
Historical role: potential alternative selectors based on price efficiency, ownership or rank strategy.

Current status: **not part of the pure Apex maximum-points recommendation**. Ownership can only be activated under a separately named rank-management objective.

## Current canonical approach
See `docs/APEX_CANONICAL_DECISION_POLICY.md`.

The production rule is:

> canonical xP → maximum-EV legal optimiser → correlated robustness diagnostics → epsilon-audited Elite secondary selector → max-EV fallback if Elite is unstable → exact GW mechanics → one published recommendation.

Historical code may remain in the repository when it is still required as a diagnostic, challenger, regression benchmark or audit trail. Keeping diagnostic code is not permission to expose multiple competing Apex teams.
