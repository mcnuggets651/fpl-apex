# Apex FPL — Current State

**Last updated:** 2026-08-08

## Production / validation
- Repository: `mcnuggets651/fpl-apex`
- Production branch: `main`
- Personal entry: `63984`
- PR #11 is merged. **Apex Unified** is the sole production team-selection path.
- PR #12 is merged. Source-health booleans are normalised to native Python booleans; the false prior-season readiness block is resolved without weakening any gate.
- The first post-PR #12 unified run is **decision-ready**: Pinnacle gate READY and the canonical builder produced a valid team.
- Publication to `main` then failed only in the Git step because internal runtime diagnostics left the worktree dirty before `git pull --rebase`.
- PR #13 (`fix/canonical-publish-clean-worktree`) fixes only that publication plumbing. It does not change projections, readiness or selection.

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

## First decision-ready canonical baseline — pre-shrinkage
Generated 2026-08-08 from Official surface:
- bootstrap hash prefix: `48004c6eb7bb`
- fixtures hash prefix: `a478e20d030d`
- canonical selector: **maximum_ev**
- reason: Elite epsilon frontier failed the explicit convergence rule
- maximum-EV horizon objective: **319.582 raw xP**
- GW1 exact-mechanics expected total: **51.53**
- captain: **Haaland**
- vice-captain: **B.Fernandes**

Canonical 15:
- GK: Verbruggen, Petrović
- DEF: Virgil, Guéhi, Thiaw, Kayode, A.Murphy
- MID: B.Fernandes, Enzo, Schade, Ndiaye, Tavernier
- FWD: Haaland, Thiago, Neave

GW1 XI:
- Verbruggen
- Guéhi, Virgil, Thiaw, Kayode
- B.Fernandes, Enzo, Schade, Ndiaye
- Haaland, Thiago

Bench:
- GK: Petrović
- outfield order: Tavernier → A.Murphy → Neave

This is the required **pre-shrinkage A/B baseline**. Do not manually replace it because individual names look surprising; the next projection upgrade exists specifically to test whether small-sample rate noise is driving any of those selections.

## Latest Elite epsilon frontier
The first decision-ready frontier is unstable, so the canonical selector correctly falls back to maximum-EV:
- 0.00% epsilon: raw xP 319.582; regret 0.00%; overlap 15/15; captain B.Fernandes
- 0.25% epsilon: raw xP 319.022; regret 0.18%; overlap 12/15; captain B.Fernandes
- 0.50% epsilon: raw xP 318.240; regret 0.42%; overlap 11/15; captain B.Fernandes
- 1.00% epsilon: raw xP 318.240; regret 0.42%; overlap 11/15; captain B.Fernandes

This is expected behaviour under the canonical convergence rule. Elite instability is diagnostic evidence, not a reason to invent another user-facing team.

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
The current projection uses direct xG90/xA90/DEFCON rates and a preseason blend, but it does not yet formally shrink small samples toward role/position priors. Empirical-Bayes / partial-pooling shrinkage is the next projection-model upgrade now that the pre-shrinkage canonical baseline exists.

## Fixture model direction
Dixon-Coles/Poisson remains a planned independent fixture expert/challenger. It should be historically validated and combined by an explicit calibrated rule rather than naively averaged into the fixture layer.

## Ownership
Ownership/effective ownership is 0% of the pure maximum-points objective. It may only be used in a separately named rank-management mode.

## Immediate next action
1. Pass CI for PR #13.
2. Merge PR #13.
3. Trigger **Apex Unified** again on `main`.
4. Confirm the decision-ready canonical recommendation is successfully committed to `main` and `apex_recommendation_latest.json` has `ready_to_act: true`.
5. Treat the team above as the official pre-shrinkage baseline and preserve its frontier/robustness evidence.
6. Implement empirical-Bayes / partial-pooling shrinkage as the next modelling PR.
7. Backtest forecast quality and rerun the identical unified pipeline plus 0/0.25/0.5/1% frontier.
8. Compare pre/post shrinkage squad overlap, captain agreement, raw-xP regret and convergence before promoting shrinkage.
9. Only after that consider the later Dixon-Coles/Poisson fixture expert.

## Current known boundaries
- Public FPL cannot expose an unpublished pre-deadline private draft; a screenshot/manual override can be newer than entry `63984`'s public state.
- Market odds remain optional unless a validated feed is configured and green.
- New-season evidence is inherently limited before competitive matches accumulate.
- The Elite epsilon is instrumented and falsifiable, but not yet historically calibrated.
- Empirical-Bayes player-rate shrinkage is not yet implemented.

## Status labels
- **Production now:** unified one-recommendation architecture; decision-ready model path verified.
- **Publishing fix now:** PR #13 cleans uncommitted runtime diagnostics before rebasing/pushing the canonical commit.
- **Captured baseline:** first pre-shrinkage maximum-EV canonical team, 319.582 horizon xP / 51.53 GW1 exact-mechanics xP.
- **Next modelling upgrade:** empirical-Bayes shrinkage for player rates, followed by pre/post frontier validation.
- **Later benchmark:** Dixon-Coles/Poisson fixture expert.
