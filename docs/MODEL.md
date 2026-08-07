# Model specification

## Objective

Apex maximises expected FPL points, not hindsight points. It uses a multi-source ensemble and a risk-adjusted optimisation objective so uncertainty in minutes and volatile output is visible rather than ignored.

## Expected minutes

Expected minutes combine:
- established starts/minutes context when available;
- preseason starts, appearances and minutes before GW1;
- official FPL status / chance of playing;
- optional verified manual availability overrides;
- conservative, auditable news headline signals.

The result is bounded to 0–90 per fixture.

## Player expected points

Per fixture the transparent model estimates:
- appearance points using probabilities of appearing and reaching 60 minutes;
- goals and assists from xG/90 and xA/90, blended conservatively with preseason samples;
- fixture-adjusted clean-sheet value with the 60-minute requirement;
- 2026/27 defensive-contribution expected value (10 CBIT for defenders; 12 CBIRT for mids/forwards; two-point cap);
- goalkeeper saves where an evidence-based saves/90 rate exists;
- a capped bonus prior;
- a small set-piece/penalty role prior.

Blank Gameweeks are explicitly zero. Double Gameweeks generate one projection row per fixture and are summed naturally.

## Ensemble

Available experts are blended row-by-row:
- official FPL immediate `ep_next`;
- Apex transparent model;
- optional AIrsenal projection;
- optional market projection.

If any expert is absent, weights are re-normalised over the evidence that actually exists. A configured risk penalty is applied to the mean using the Apex model uncertainty estimate.

## Initial squad MILP

The optimiser enforces:
- £100.0m budget;
- 15 players;
- 2 GK / 5 DEF / 5 MID / 3 FWD;
- maximum three per club;
- legal starting XI formation;
- one captain;
- lock/ban scenario constraints.

Apex runs unrestricted plus Haaland and no-Haaland scenarios when requested.

## Multi-Gameweek transfer MILP

When a current squad is supplied, Apex jointly optimises each Gameweek's squad, XI, captain, transfers and cash. It models the official free-transfer state exactly from 1–5 using a discrete state transition and charges four points per transfer above the available allowance. Current snapshot prices are held fixed across the planning horizon rather than guessing future price moves.

Fixed Wildcard, Bench Boost and Triple Captain weeks are supported by the engine. Free Hit is kept separate from permanent transfer planning because its squad-reversion semantics require a one-week temporary-squad scenario.

## Calibration

`apex-fpl backtest` calculates MAE, RMSE, bias and rank correlation from historical prediction/actual CSVs. Model weights should be changed only after repeatable backtests, not because of one surprising match.
