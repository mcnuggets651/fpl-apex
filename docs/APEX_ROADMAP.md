# Apex FPL — Roadmap

Operating authority: [`APEX_OPERATING_MANUAL.md`](APEX_OPERATING_MANUAL.md).

## Current milestone — finish the 28 August production-authority cutover

1. Merge the audited AIrsenal-only production xP cutover after final branch CI/governance.
2. Run the repaired FPL Core enrichment refresh and validate/pin the then-current upstream candidate.
3. Refresh pinned AIrsenal and require complete current player/Gameweek coverage.
4. Run Apex Unified from a fresh Official FPL snapshot.
5. Verify one sealed bundle/generation across optimiser, parity, exact mechanics, final evidence and answer context.
6. Publish a recommendation only if `safe_to_act=true` and `ready_to_act=true`.

## Immediate operational repair — prospective learning

GW1 is complete but the genuine deadline archive is not yet present/active and calibration still has 0 completed Gameweeks. Before treating Apex's learning/promotion loop as operational:

1. ensure production/shadow provider rows are frozen before each deadline;
2. persist immutable deadline/provider/snapshot/player/GW identity;
3. join Official outcomes only after the event;
4. verify no-hindsight firewall tests;
5. produce the first real provider comparison only when genuine completed forecasts exist.

No post-event reconstruction may be labelled prospective.

## Production foundations already implemented

- Official FPL factual universe and all-player truth protections;
- content-addressed DecisionBundle and offline audit/replay;
- pinned AIrsenal worker;
- Apex proprietary transparent shadow projection surface;
- FPL Core/Understat enrichment and validation paths;
- legal maximum-EV optimisation;
- exact current FPL mechanics;
- correlated scenario/CVaR and force/ban regret diagnostics;
- independent solver parity;
- personal entry synchronisation for 63984;
- receding-horizon current-team strategy;
- final selected-player evidence identity;
- one user-facing answer/recommendation contract;
- prospective calibration framework and explicit promotion gate.

## Current forecast authority

AIrsenal is the sole production statistical xP provider. Apex proprietary xP, Official EP and market surfaces have zero production forecast weight. The old fixed three-way blend is retired.

This remains in force until a challenger wins genuine prospective promotion; it is not a cue to hand-tune another blend.

## Next modelling milestone — only after prospective evidence exists

The highest-value modelling work is challenger evaluation rather than speculative complexity:

- compare AIrsenal vs Apex shadow forecast error/ranking/calibration on frozen current-season rows;
- evaluate minutes/start calibration by cohort;
- evaluate small-sample/shrinkage variants;
- evaluate Understat/team-strength challenger value;
- quantify whether any challenger changes actual transfer/squad/captain decisions beneficially;
- promote nothing until the governed minimum sample/evidence bar passes.

## V2 architecture programme

Draft PRs #67–#88 remain withheld. Their valuable mechanisms may be reused, but the stack must first be rebased/requalified against the current AIrsenal-only authority because later heads still assume the retired Apex/Official/AIrsenal blend.

Do not merge the V2 stack wholesale simply because its synthetic/engineering checks are green. Production cutover requires exact identity, live evidence, performance and dependency qualification.

## High-value future upgrades

Only after the current production/learning loop is demonstrably healthy:

- validated market-implied goal/clean-sheet/scorer probabilities;
- calibrated Bayesian minutes/start/appearance model;
- richer penalty/set-piece inference with provenance;
- DEFCON threshold-probability calibration;
- bonus/BPS simulation if it adds prospective value;
- calibrated match/fixture stochastic modelling;
- price-change timing model for transfer option value;
- chip opportunity-cost modelling;
- optional explicit rank-utility/EO mode separate from pure maximum points;
- bounded evaluation of reproducible external projection challengers such as OpenFPL-style systems.

## Definition of “Apex 10.0”

Not perfect foresight. It means the strongest current reproducible process:

- correct Official facts;
- a qualified current statistical forecast provider;
- exact legal FPL decision mechanics;
- current football evidence with provenance;
- independent assurance and robustness diagnostics;
- no-hindsight prospective learning;
- one unambiguous actionable output when—and only when—the gates pass.
