# Apex FPL — Session Log

Append concise records after meaningful project sessions. This is continuity context, not a replacement for Git history.

## 2026-08-11 — Decision-surface architecture repair, PR 1

### Finding
Pinnacle and Elite independently reran the live pipeline. Canonical publication
checked only Official FPL hashes, so other evidence, configuration and projections
could drift while still being described as the same surface.

### Implementation
- Added a content-addressed, credential-safe decision bundle.
- Added exact hashes for all material inputs and persisted player/projection frames.
- Removed live retrieval from Pinnacle and Elite.
- Added bundle-aware parity and canonical gates.
- Added lineage audit, offline replay and workflow artifact retention.

### Local evidence
- 174/174 tests pass.
- Ruff, governance, seven upstream pins and all workflow YAML files pass.
- A production-shaped smoke capture sealed 577 players, 380 fixtures, 604
  preseason rows and 4,616 player/Gameweek projections, then passed a fresh
  artifact/hash audit.

### Boundary
No production activation claim until PR, CI, merge and fresh Apex Unified output.

## 2026-08-08 — Shrinkage must revalidate frontier stability
### Context
Final architecture review agreed that empirical-Bayes shrinkage should not be judged only by player-level forecast error. Some apparent Elite epsilon instability may currently be caused by noisy low-minute player rates rather than genuine squad-selection uncertainty.

### Decision
After implementing shrinkage, rerun the identical canonical maximum-EV + epsilon frontier and compare it against the pre-shrinkage baseline. Required comparison: raw-xP regret, 15-player overlap, captain agreement and convergence status at 0.25%, 0.50% and 1.00%. Improved or preserved frontier stability is a useful sanity signal that shrinkage reduced projection noise. A shrinkage model that destabilises the frontier without improving no-hindsight forecast performance is not promoted automatically.

### Sequencing unchanged
1. Finish/merge the unified recommendation architecture first.
2. Produce the first canonical Apex team.
3. Implement empirical-Bayes shrinkage as a separate projection-model PR.
4. Backtest player forecast performance and rerun the epsilon frontier.
5. Only then consider later fixture-model additions such as Dixon-Coles.

## 2026-08-08 — Unified single-recommendation architecture
### Context
The repository had accumulated several internal selection outputs (maximum-EV/Pinnacle, Elite, CVaR/safety and scenario candidates). Even when mathematically useful as challengers, exposing them as separate "Apex teams" created conversational drift and inconsistent recommendations.

### Decision
Apex now has one user-facing recommendation contract. Internal models remain because they are needed to challenge and falsify the decision, but they are no longer separate recommendation paths.

### Implementation in PR #11
- Added `scripts/run_apex.py` as the single production command.
- Added `scripts/build_canonical_recommendation.py` as the deterministic canonical selector/publisher.
- Added `data/generated/apex_recommendation_latest.json` / `.md` as the only user-facing team output.
- Changed the GitHub production workflow to **Apex Unified** and stopped publishing internal Pinnacle/Elite candidate teams to main.
- Internal Pinnacle/Elite outputs remain workflow artifacts for audit/debugging only.
- Added Official FPL snapshot identity to Elite diagnostics so the canonical builder can reject mismatched surfaces.
- Added exact captain/vice/autosub mechanics to the Elite-selected 15 before it can become canonical.
- The canonical selector automatically uses Elite only when the epsilon convergence rule passes; otherwise it falls back to maximum-EV.
- Archived superseded standalone selection philosophies under `archive/selection_approaches/`.
- Added `APEX_CANONICAL_DECISION_POLICY.md` and updated README, Master Context, Operating Manual, Architecture, Current State and Decisions.

### Canonical rule
`xp -> maximum-EV -> correlated robustness diagnostics -> epsilon-audited Elite secondary selector -> maximum-EV fallback if unstable -> exact GW mechanics -> one published recommendation.`

### Next actions
1. Pass PR #11 CI after the unified changes.
2. Merge PR #11 if green.
3. Trigger Apex Unified once on `main`.
4. Confirm `apex_recommendation_latest.json` has `ready_to_act=true` and matched snapshot identity.
5. Read that file as the one Apex team and explain its Haaland/no-Haaland/epsilon/robustness evidence.
6. Compare against the user's current private screenshot if still current.
7. Then implement empirical-Bayes player-rate shrinkage and benchmark whether it changes the canonical recommendation.

## 2026-08-08 — Follow-up architecture audit: shrinkage, minutes and epsilon
### Context
A second review challenged four remaining areas before PR #11 merge: small-sample shrinkage, explicit minutes modelling, the arbitrary 0.5% Elite epsilon, and future fixture-ensemble combination rules.

### Findings
- Minutes is already a first-class Apex submodel. `minutes_profile` combines prior-season starts/minutes, current-season team matches, preseason starts/minutes, official availability, manual/news multipliers, start/appearance/60+/80+ probabilities and a confidence score. This is structurally sound enough for the current PR, though future calibration can improve it.
- Formal empirical-Bayes shrinkage of player attacking rates is missing. The current projection blends established xG90/xA90/DEFCON inputs with preseason based on preseason minutes, but does not shrink small-sample player rates toward position/role priors. This is now the next projection-model priority.
- The 0.5% Elite epsilon is not empirically calibrated. Rather than hide that, every live Elite run now emits an unrestricted epsilon frontier at 0%, 0.25%, 0.5% and 1.0% so the final decision can see how much raw xP is sacrificed and how much the squad changes.
- Future fixture experts must not be naively averaged. Any Dixon-Coles/Poisson addition should enter as a benchmarked expert/challenger with an explicit historically validated combination rule.

### PR #11 additions
- Added live epsilon sensitivity frontier reporting.
- Marked epsilon as uncalibrated in the Elite contract.
- Added Project Brain decisions for sample-size shrinkage and epsilon sensitivity.
- Added known-issue entries K009/K010.
- Updated CURRENT_STATE with minutes-model status and the next modelling priority.

### Decision
Do not block the safer lexicographic selection architecture on an unrelated projection-model refactor. Merge PR #11 only if CI is green, but do not allow Elite to override maximum-EV in the final squad until the synchronized live epsilon frontier is inspected. The next modelling PR after the squad comparison is empirical-Bayes shrinkage for player attacking rates, ahead of Dixon-Coles.

## 2026-08-08 — Probabilistic xPts architecture review and Elite lexicographic correction
### Context
Before merging PR #11, an alternative architecture was proposed: recency-weighted Dixon-Coles/Poisson team strength -> player xPts -> constrained optimiser -> ownership tiebreak -> Monte Carlo uncertainty. The proposal's core criticism of a single weighted selection score was valid.

### Review outcome
Apex already follows most of the stronger architecture through Pinnacle: canonical xPts, legal MILP optimisation, rolling horizon, correlated stochastic scenarios/CVaR, exact mechanics and multiple evidence sources. The weakest part was Elite, which still risked turning preference weights into a pseudo-forecast.

Three proposed weak links were explicitly rejected in their literal form:
- Dixon-Coles/Poisson is useful as an independent fixture expert/challenger, not the sole team-strength truth.
- Player xPts should not be allocated mechanically by historical share of team xG; use direct player rates, minutes, role, set pieces and opponent context with shrinkage where needed.
- Ownership is not part of a maximum-points objective. It belongs only in an explicit rank-management/tiebreak mode.

The uncertainty proposal was accepted in principle but strengthened: scenarios must preserve correlated team/player/minutes outcomes rather than draw independent noise around each player's mean.

### Decision
Replace the proposed ±5% Elite xP modifier with a lexicographic / epsilon-constraint design.

### Implementation in PR #11
- Stage 1 solves maximum canonical Pinnacle xP for unrestricted, Haaland and no-Haaland independently.
- Stage 2 maximises Elite 35/20/15/10/10/5/5 utility only inside a provisional raw-xP regret band relative to that scenario's own maximum.
- The selected 15 are then locked and XI/captain/vice are re-optimised on raw xP.
- `optimise_initial_horizon` now supports a reference projection objective floor and a separate display projection surface.
- Added tests proving a secondary objective cannot violate an exact raw-xP floor and can choose alternatives only when the floor permits it.
- Elite remains an explanatory/secondary selector, never a second expected-points forecast.
- Project Brain decision, model and current-state documents updated.

### Next actions
1. Pass PR #11 CI under the lexicographic design.
2. Merge only if green.
3. Generate one synchronized live Pinnacle + Elite snapshot including epsilon sensitivity.
4. Compare unrestricted, Haaland and no-Haaland on raw xP and stochastic robustness.
5. Add empirical-Bayes player-rate shrinkage as the next model upgrade.
6. Benchmark a Dixon-Coles/Poisson fixture expert later as a separate improvement.
7. Publish the final Apex squad only after the synchronized comparison.

## 2026-08-08 — First Elite live-output diagnosis
### Context
The first live Elite 10.0 output exposed a conceptual flaw: percentile/rank utility was being optimised directly. The unrestricted Elite squad scored 313.851 raw xP versus 319.582 for maximum-EV (5.731 xP / ~1.8% regret), and the report displayed Elite utility values under a `gw1_xp` heading.

### Lesson
A preference utility must not masquerade as expected points. The first proposed correction was a bounded ±5% xP modifier, but architecture review before merge led to the stronger lexicographic design recorded above.

## 2026-08-08 — Project Brain creation
### Context
Repeated project conversations were losing continuity between current production state, proposed architecture and squad recommendations.

### Actions
- Established a canonical documentation system.
- Defined startup/continuity protocol.
- Recorded current Pinnacle/Elite relationship.
- Recorded Elite 10.0 weighting and safeguards.
- Separated production, validation-needed and proposed states.
- Added benchmark, known-issues and vision registers.

### Current state
Elite 10.0 is merged. The next modelling task is to run/inspect its latest live output and compare it against Pinnacle rather than continue theoretical squad tweaking.

### Next actions
1. Validate latest Elite output.
2. Benchmark raw xP and Elite utility versus Pinnacle.
3. Compare the user's current private draft with both engines.
4. Only then decide whether Meta optimisation is necessary.

## 2026-08-07 — Elite 10.0 implementation
### Decision
Correct the observed low-ceiling/value bias without replacing canonical expected points.

### Implementation
Added an Elite utility with 35/20/15/10/10/5/5 weighting and raw-xP regret reporting. PR #6 passed the configured Apex FPL workflow and was merged.

### Lesson
A green CI run proves configured software checks passed; it does not prove a new decision objective improves FPL outcomes. Benchmarking remains mandatory.
