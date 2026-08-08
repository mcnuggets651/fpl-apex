# Apex FPL — Current State

**Last updated:** 2026-08-08

## Production / validation
- Repository: `mcnuggets651/fpl-apex`
- Production branch: `main`
- Personal entry: `63984`
- PR #11 now contains the unified recommendation architecture and is under CI validation.
- Prior-season evidence/captain-stability blockers were resolved by PR #10 and are green on main.

## One canonical approach
Apex now has one intended user-facing decision path:

**canonical xP → maximum-EV legal optimiser → correlated robustness diagnostics → epsilon-audited Elite secondary selector → maximum-EV fallback if Elite is unstable → exact GW mechanics → one recommendation.**

The only user-facing output is:
- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`

The only production command is:

```bash
python scripts/run_apex.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
```

Pinnacle, Elite, CVaR, regret and solver-parity outputs are internal diagnostics/challengers only. Historical standalone selection philosophies are archived under `archive/selection_approaches/`.

## Selection policy
1. `xp` is the canonical expected-points forecast.
2. Solve maximum raw xP under FPL constraints.
3. Run correlated scenario/CVaR/regret/captain stability diagnostics.
4. Elite uses the 35/20/15/10/10/5/5 evidence profile only as a secondary objective in a near-optimal xP set.
5. Audit epsilon at 0%, 0.25%, 0.5% and 1.0%.
6. Elite may influence the 15 only if 0.25%, 0.5% and 1.0% each retain at least 13/15 max-EV players and the same captain.
7. If the frontier fails, maximum-EV is the automatic canonical fallback.
8. Re-optimise XI, captain, vice and bench mechanics on raw xP.
9. Publish only if safety, full-data, Pinnacle readiness and snapshot-consistency gates pass.

## Minutes model status
Expected minutes is already a first-class Apex submodel. `minutes_profile` combines prior-season start/minute evidence, current-season team matches, preseason starts/minutes, official availability, manual/news multipliers and explicit start/appearance/60+/80+ probabilities with a minutes-confidence output.

## Player-rate model gap
The current projection uses direct xG90/xA90/DEFCON rates and a preseason blend, but it does not yet formally shrink small samples toward role/position priors. Empirical-Bayes / partial-pooling shrinkage is the next projection-model upgrade.

## Fixture model direction
Dixon-Coles/Poisson remains a planned independent fixture expert/challenger. It should be historically validated and combined by an explicit calibrated rule rather than naively averaged into the fixture layer.

## Ownership
Ownership/effective ownership is 0% of the pure maximum-points objective. It may only be used in a separately named rank-management mode.

## Immediate next action
1. Pass CI for the unified PR #11.
2. Merge PR #11 if green.
3. Trigger **Apex Unified** once on `main`.
4. Confirm `apex_recommendation_latest.json` is generated from one matched official snapshot and has `ready_to_act: true`.
5. Read that file as the only team recommendation.
6. Inspect epsilon convergence, Haaland/no-Haaland and robustness diagnostics to explain the choice—not to create competing teams.
7. Compare the canonical team to the user's private screenshot draft if still current.
8. Then implement empirical-Bayes player-rate shrinkage as the next modelling PR and benchmark whether it changes the canonical squad.

## Current known boundaries
- Public FPL cannot expose an unpublished pre-deadline private draft; a screenshot/manual override can be newer than entry `63984`'s public state.
- Market odds remain optional unless a validated feed is configured and green.
- New-season evidence is inherently limited before competitive matches accumulate.
- The Elite epsilon is instrumented and falsifiable, but not yet historically calibrated.
- Empirical-Bayes player-rate shrinkage is not yet implemented.

## Status labels
- **Production now:** current Pinnacle/data/robustness stack on `main`.
- **Validation now:** PR #11 unified single-recommendation contract.
- **Next after merge:** one live Apex Unified run and final squad readout.
- **Next modelling upgrade:** empirical-Bayes shrinkage for player rates.
- **Later benchmark:** Dixon-Coles/Poisson fixture expert.
