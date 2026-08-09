# Apex FPL — Benchmarks

## Purpose
Every material modelling/selection change must be compared against a stable baseline. CI success is not a modelling benchmark.

## Required benchmark fields
For each candidate engine/version record:
- timestamp/source snapshot
- horizon
- legal squad and cost
- GW1 XI/captain/vice
- raw ensemble xP (GW1 and horizon)
- decision utility if applicable
- EV regret versus maximum-EV Pinnacle
- expected minutes/start-risk summary
- stochastic mean/floor/CVaR where available
- captaincy contribution
- solver parity status
- material source/readiness warnings
- eventual no-hindsight realised result once available

## Baseline: Pinnacle
Pinnacle maximum-EV on ensemble `xp` is the default comparison baseline. It should not be displaced by a new objective without evidence.

## Candidate: Elite 10.0
Hypothesis: reducing value weight and explicitly rewarding attack/minutes/captaincy will remove questionable low-ceiling picks while preserving most raw expected points and improving elite scoring potential.

Initial weights: `35/20/15/10/10/5/5`.

### Required first post-merge test
- latest unrestricted Pinnacle vs Elite
- Haaland Pinnacle vs Elite
- no-Haaland Pinnacle vs Elite
- exact raw-xP regret
- player-level changes and reason codes
- minutes/ceiling/captaincy changes

**Status:** completed. The latest decision-ready canonical run falls back to
maximum-EV because the 0.25%, 0.50% and 1.00% Elite solutions retain only
12/15, 11/15 and 11/15 of the maximum-EV squad. Captain agreement alone does
not satisfy the convergence rule.

## Candidate: Understat team strength

PR #16 is merged in shadow mode. Its held-out component comparison covered 197
matches; the combined component reported xG RMSE 0.688945 versus 0.707822 for
Understat alone and 0.708604 for Elo alone. The challenger did not alter the
canonical 15 or captain and is not a production replacement.

## Candidate: empirical-Bayes player-rate shrinkage

The first PR #14 green result is withdrawn: prediction cohorts were filtered by
future minutes/outcome availability before empirical priors and live-price tiers
were calculated. PR #18 replaces it with complete-roster predictions that apply
future eligibility only after predictions are frozen and report pre-GW1, GW1-5
and GW6+ strata separately.

Corrected attacking-rate RMSE ratios (shrunk/raw):

- xG90: 0.923542 in 2024/25; 0.731473 in 2025/26;
- xA90: 0.833267 in 2024/25; 0.916736 in 2025/26.

All four attacking-rate shadow gates pass. DEFCON fails its separate gate and is
a no-op by default.

The 2024/25 and 2025/26 seasons have been inspected during model development.
They are useful chronological evaluation seasons but are not independent final
holdouts. Shrinkage remains dormant even after the corrected shadow pass;
activation requires a separate PR and explicit decision.

## Promotion rule
Do not tune weights to fit a preferred squad. Record hypotheses before evaluating outcomes and use the no-hindsight archive as the season grows.
