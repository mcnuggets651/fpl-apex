# Apex FPL — Current State

**Last updated:** 2026-08-08

## Production / validation
- Repository: `mcnuggets651/fpl-apex`
- Production branch: `main`
- Personal entry: `63984`
- PR #11 is merged. **Apex Unified** is now the sole production team-selection path.
- Apex Unified run #36 completed successfully at system level but correctly withheld a recommendation because Pinnacle readiness reported the prior-season source unhealthy.
- The run artifact proves the underlying prior-season evidence is actually healthy: 570 current official IDs with **80.2% prior playing-time coverage**, above the 70% production floor.
- Root cause is a type-normalisation bug: `previous_coverage >= 0.70` can produce `numpy.bool_(True)`, which was serialized as the string `"True"`; the readiness gate deliberately accepts only native boolean `true`.
- Fix branch: `fix/source-status-native-bools`. The fix normalises source status booleans at the provenance boundary and adds regression tests. No readiness threshold is being weakened.

## One canonical approach
Apex has one user-facing decision path:

**canonical xP → maximum-EV legal optimiser → correlated robustness diagnostics → epsilon-audited Elite secondary selector → maximum-EV fallback if Elite is unstable → exact GW mechanics → one recommendation.**

The only user-facing output is:
- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`

The only production command is:

```bash
python scripts/run_apex.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
```

Pinnacle, Elite, CVaR, regret and solver-parity outputs are internal diagnostics/challengers only. Historical standalone selection philosophies are archived under `archive/selection_approaches/`.

## Latest unified selection evidence
The first post-merge Elite epsilon frontier was unstable, so the canonical selector correctly chose **maximum_ev** rather than Elite:
- 0.00% epsilon: 15/15 overlap vs max-EV; captain B. Fernandes
- 0.25% epsilon: 12/15 overlap; captain B. Fernandes
- 0.50% epsilon: 11/15 overlap; captain B. Fernandes
- 1.00% epsilon: 11/15 overlap; captain B. Fernandes

This is expected behaviour under the canonical convergence rule; Elite instability is not the current readiness blocker.

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
The current projection uses direct xG90/xA90/DEFCON rates and a preseason blend, but it does not yet formally shrink small samples toward role/position priors. Empirical-Bayes / partial-pooling shrinkage is the next projection-model upgrade after the first ready canonical baseline is captured.

## Fixture model direction
Dixon-Coles/Poisson remains a planned independent fixture expert/challenger. It should be historically validated and combined by an explicit calibrated rule rather than naively averaged into the fixture layer.

## Ownership
Ownership/effective ownership is 0% of the pure maximum-points objective. It may only be used in a separately named rank-management mode.

## Immediate next action
1. Merge the native-boolean source-status fix after CI is green.
2. Trigger **Apex Unified** again on `main`.
3. Confirm the prior-season source is emitted with native `ok: true` and Pinnacle readiness passes.
4. Confirm `apex_recommendation_latest.json` has `ready_to_act: true` and matched Official FPL hashes.
5. Read that file as the first canonical Apex baseline team.
6. Record squad, XI, captain, vice, bench order, raw xP, Haaland/no-Haaland diagnostics, epsilon frontier and robustness.
7. Then implement empirical-Bayes player-rate shrinkage as a separate modelling PR.
8. Rerun the identical unified pipeline and epsilon frontier and compare pre/post shrinkage before promotion.

## Current known boundaries
- Public FPL cannot expose an unpublished pre-deadline private draft; a screenshot/manual override can be newer than entry `63984`'s public state.
- Market odds remain optional unless a validated feed is configured and green.
- New-season evidence is inherently limited before competitive matches accumulate.
- The Elite epsilon is instrumented and falsifiable, but not yet historically calibrated.
- Empirical-Bayes player-rate shrinkage is not yet implemented.

## Status labels
- **Production now:** unified one-recommendation architecture on `main`.
- **Bug fix now:** native boolean normalisation for source-health provenance.
- **Next production milestone:** first `ready_to_act=true` canonical recommendation.
- **Next modelling upgrade:** empirical-Bayes shrinkage for player rates, followed by pre/post frontier validation.
- **Later benchmark:** Dixon-Coles/Poisson fixture expert.
