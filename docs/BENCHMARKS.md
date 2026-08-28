# Apex FPL — Benchmarks

## Purpose
Every material forecast/provider/selection change must be compared against a stable predeclared baseline. CI success is an engineering prerequisite, not modelling evidence.

## Current production baseline

**Forecast:** validated AIrsenal xP on the exact Official FPL player/Gameweek surface.  
**Decision:** Apex legal maximum-EV/receding-horizon optimiser and exact FPL mechanics.

Apex proprietary xP is now a shadow challenger, not part of the production forecast baseline.

## Required prospective provider benchmark fields

For each frozen provider/player/Gameweek row record:

- season and Gameweek;
- deadline timestamp;
- forecast timestamp;
- Official snapshot identity;
- player ID / club / FPL position / current price;
- provider and provider version;
- production vs shadow authority;
- xP;
- expected-minutes/start/appearance fields where available;
- later Official realised points/participation joined only after the event.

Aggregate evaluation should include calibration/ranking/error metrics, Gameweek-block uncertainty, cohorts (position/price/minutes/new transfers where useful) and decision-impact comparisons.

## Required decision benchmark fields

For each candidate decision policy/version record:

- exact sealed bundle/snapshot/provider identity;
- current squad/cash/FT state where applicable;
- legal action and post-action squad;
- XI/captain/vice/bench;
- canonical expected points;
- exact mechanics result;
- static/near-equivalent regret where useful;
- stochastic mean/floor/CVaR diagnostics;
- solver parity status;
- source/readiness warnings;
- later no-hindsight realised outcome after the action was frozen.

## Current promotion baseline

No forecast challenger has enough genuine 2026/27 prospective evidence for production promotion. At the 28 August 2026 audit:

- completed genuine Gameweeks: 0;
- active calibration rows: 0;
- promotion: blocked.

Therefore no retrospective benchmark, appealing squad or synthetic V2 certification may justify replacing AIrsenal production authority yet.

## Historical benchmark evidence — retained for research only

### Elite frontier
Historical Elite/equivalence diagnostics showed that small epsilon changes could materially alter the 15. This supported keeping secondary utilities diagnostic rather than allowing them to become a separate production selector. Those results remain architecture history; they are not a forecast-provider benchmark under the current authority contract.

### Understat team-strength challenger
PR #16 historical held-out component comparison covered 197 matches; the combined component reported xG RMSE 0.688945 versus 0.707822 for Understat alone and 0.708604 for Elo alone. This evidence remains useful research history but did not grant Understat production xP authority.

### Empirical-Bayes player-rate shrinkage
Corrected historical attacking-rate RMSE ratios (shrunk/raw) previously reported:

- xG90: 0.923542 in 2024/25; 0.731473 in 2025/26;
- xA90: 0.833267 in 2024/25; 0.916736 in 2025/26.

Those seasons influenced development and are not independent final holdouts. DEFCON failed its separate gate. These results keep the challenger interesting but do not authorize production forecast activation.

## Promotion rule

Do not tune provider weights, model features, epsilon bands or named-player assumptions to fit a preferred squad. Record the hypothesis before outcomes, freeze the challenger before deadlines, evaluate after outcomes, and promote only after the current governance threshold and explicit review are satisfied.
