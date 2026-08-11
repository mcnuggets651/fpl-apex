# Apex FPL — Master Context

**Canonical project brain. Read this before making any Apex recommendation or architectural change.**

## Mission
Build the strongest auditable Fantasy Premier League decision engine possible: maximise expected FPL points and elite scoring ceiling while explicitly measuring uncertainty, minutes risk, downside and model disagreement.

## Repository
- Production repository: `mcnuggets651/fpl-apex`
- Production branch: `main`
- Personal FPL entry: `63984`
- Season focus: 2026/27

## Non-negotiable principles
1. Official FPL is canonical for identity, club, position, price, status and fixtures.
2. Never select a squad from memory or generic FPL opinion when current generated outputs exist.
3. Raw ensemble expected points (`xp`) are the canonical forecast.
4. Expected minutes/start/appearance probability is a first-class model input.
5. The legal maximum-xP optimiser generates the near-optimal candidate frontier.
6. Elite is a diagnostic frontier inside an epsilon-audited near-optimal xP set.
7. Exact full-horizon mechanics rescoring produces the only canonical `Decision`, regardless of Elite convergence.
8. CVaR, regret, captain stability and independent solvers are robustness diagnostics, not separate user-facing teams.
9. Ownership is excluded from the pure maximum-points objective.
10. Every recommendation must be reproducible, explainable and traceable to a current run.
11. A red data/readiness/snapshot-consistency gate blocks an Apex-labelled recommendation.
12. Football randomness cannot be eliminated; confidence must never be presented as certainty.
13. Never claim a unique optimum when solver bounds or the disclosed equivalence band contain alternatives.

## One production recommendation
Apex has **one** user-facing decision contract:

- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`

The canonical production command is:

```bash
python scripts/run_apex.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
```

When the user asks for “the Apex team”, this contract is the answer. Internal Pinnacle, Elite, CVaR, regret and solver outputs exist to construct/challenge that answer, not to create several competing Apex teams.

## Unified decision flow
Official FPL → validated enrichment → first-class minutes model → canonical player xP ensemble → near-optimal legal squad shortlist → exact full-horizon XI/captain/vice/bench/autosub rescoring → **one canonical Decision**, with equivalence, correlated robustness and Elite epsilon audits attached as diagnostics.

### Elite convergence diagnostic
Elite reports whether the 0.25%, 0.50% and 1.00% epsilon solutions each:
- retain at least 13/15 of the maximum-EV squad; and
- keep the same captain as maximum-EV.

This evidence never changes the canonical maximum-EV selection.

## Internal diagnostic layers
### Maximum-EV / Pinnacle
The auditable search baseline: maximise ensemble-mean xP under FPL legality and horizon constraints, enumerate distinct near-optimal squads, then select only after exact-mechanics horizon rescoring.

### Elite
Secondary evidence lens only. Weight profile remains:
- 35% attacking returns
- 20% expected minutes/start probability
- 15% captaincy value
- 10% set pieces and penalties
- 10% fixture quality
- 5% bonus and DEFCON
- 5% price efficiency

Elite never creates or modifies expected points.

### Robustness
Correlated scenarios, CVaR, exact force/ban regret, captain stability, exact mechanics and independent solver parity expose fragility. They do not silently substitute another objective.

## Projection-model next priority
The main known projection gap is formal empirical-Bayes/partial-pooling shrinkage of small-sample player attacking rates toward role/position priors. This is the next modelling upgrade after the unified recommendation is validated. Dixon-Coles/Poisson is a later fixture-expert benchmark, not a new selection philosophy.

## Expected decision output
The canonical recommendation should contain the legal 15-man squad, GW XI, captain, vice, bench order, horizon objective, exact GW mechanics, readiness status, epsilon convergence evidence, Haaland/no-Haaland scenarios when relevant and robustness diagnostics.

## Continuity protocol
Before substantive Apex work read, in order:
1. `docs/CURRENT_STATE.md`
2. this file
3. `docs/APEX_DECISIONS.md`
4. `docs/APEX_CANONICAL_DECISION_POLICY.md`
5. `docs/APEX_OPERATING_MANUAL.md`
6. `data/generated/apex_recommendation_latest.json`

Only then inspect internal diagnostics if needed. Continue from the latest state rather than reconstructing the project from chat history.

## Related canonical documents
- [Canonical decision policy](APEX_CANONICAL_DECISION_POLICY.md)
- [Current state](CURRENT_STATE.md)
- [Decisions](APEX_DECISIONS.md)
- [Architecture](APEX_ARCHITECTURE.md)
- [Model specification](APEX_MODEL_SPEC.md)
- [Data sources](APEX_DATA_SOURCES.md)
- [Operating manual](APEX_OPERATING_MANUAL.md)
- [Roadmap](APEX_ROADMAP.md)
- [Benchmarks](BENCHMARKS.md)
- [Known issues](KNOWN_ISSUES.md)
- [Charter](APEX_CHARTER.md)
- [Vision](VISION.md)
- [Session log](SESSION_LOG.md)
