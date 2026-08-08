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

**Status:** pending latest live post-merge Elite run/inspection.

## Promotion rule
Do not tune weights to fit a preferred squad. Record hypotheses before evaluating outcomes and use the no-hindsight archive as the season grows.
