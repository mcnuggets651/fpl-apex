# Apex V2 — Scenario Robustness and Convergence

## Status

This document defines the Slice 9 operating contract for robustness diagnostics. Slice 9 does **not** create recommendation authority and does not replace the canonical expected-value objective.

The production registry currently contains no qualified scenario-generator champion and no qualified convergence-policy champion. Therefore Slice 9 remains shadow/assurance infrastructure until empirical qualification is supplied by later governance work.

## Boundary: generation happens outside the decision runtime

The post-seal decision runtime never creates random scenarios. A separate worker may generate a joint scenario stream, but the decision runtime accepts only a retained immutable `ScenarioSet` artifact.

The sealed artifact identifies:

- the exact `ForecastId` it is intended to reconcile against;
- the `ScenarioGeneratorId`;
- generator/RNG algorithm identity;
- integer seed;
- ordered scenario ordinals;
- integer scenario weights;
- every player/Gameweek outcome in every scenario;
- source artifact identities.

Changing the seed, order, weight or any outcome changes semantic identity.

`decision.robustness`, `decision.scenario_store` and `control.scenario_registry` are forbidden from importing runtime RNGs, numpy/scipy/pandas, network clients, V1 services/optimisers or other hidden generation paths.

## Joint dependence is explicit

Slice 7 `PlayerFixtureScenario` labels describe marginal player/fixture forecast distributions. Matching labels across different players are **not** evidence that those rows form a joint correlated scenario.

Only an explicitly governed joint generator may create cross-player or cross-fixture dependence for Slice 9. The scenario runtime therefore does not import or reinterpret marginal Slice 7 scenario labels as correlation structure.

This prevents accidental perfect correlation, accidental independence, and index-alignment artefacts from masquerading as football dependence.

## Common random numbers

All compared actions are scored against the same ordered scenario stream. Apex never gives one action a favorable random sample and another action a different sample.

Convergence checkpoints are nested prefixes of that one stream. For example, a 512-scenario checkpoint contains exactly scenarios 1–512 and the 256 checkpoint contains exactly scenarios 1–256 of the same stream.

The order is part of `ScenarioSetId`, so a reordered sample is a different scenario set.

## The 256-scenario rule

`256` is a historical minimum floor, not proof of convergence.

A governed `ScenarioConvergencePolicy` requires at least two increasing checkpoint counts, each at least 256. A run with only 256 usable scenarios cannot prove convergence because there is no broader nested checkpoint against which stability can be demonstrated.

If the required broader checkpoint is unavailable, Apex returns `INCONCLUSIVE`; it does not reuse an old convergence certificate or assume the smaller run is stable.

## Fixed submitted-action scoring

A `DecisionAction` is frozen before scenario scoring. Each scenario evaluates that submitted action exactly as FPL would realize it. There is no scenario-specific hindsight optimization.

Slice 9 therefore preserves:

- the submitted 15;
- submitted XI;
- captain and vice-captain;
- goalkeeper bench slot;
- ordered outfield bench;
- chip choice;
- transfer-hit cost.

Per scenario, the scorer applies realized FPL behavior:

- captain bonus when the captain appears;
- vice-captain fallback when the captain does not appear;
- Triple Captain multiplier;
- Bench Boost;
- goalkeeper substitution;
- legal ordered outfield autosubs subject to formation constraints;
- hit subtraction.

A scenario never gets to choose a different XI, captain or bench order after seeing outcomes.

## Scenario outcome unit

A `JointPlayerGameweekOutcome` is one player's realized aggregate FPL points for one Gameweek in one joint scenario, plus whether the player appeared.

For a normal single-fixture Gameweek, the worker aggregates that fixture into the player/Gameweek outcome. For a Double Gameweek, the worker must aggregate all fixtures in that Gameweek consistently into the single player/Gameweek value before sealing the joint scenario set. This lets the decision scorer operate on the FPL Gameweek action while the forecast-reconciliation layer compares against the sum of canonical fixture-level Forecast expectations for that player/Gameweek.

A non-appearing player must have zero points in the scenario contract.

## Exact robustness metrics

Scenario weights and realized points are integers. Runtime aggregation uses exact rational arithmetic rather than floating-point tolerances hidden in implementation code.

For an action with scenario score `s_i` and positive integer weight `w_i`:

- weighted mean = `sum(w_i * s_i) / sum(w_i)`;
- lower quantile is the governed weighted lower-tail quantile;
- lower CVaR is the exact weighted average of the worst governed probability mass, including fractional use of the boundary scenario weight when required.

`ScenarioConvergencePolicy` owns the CVaR alpha, lower-quantile probability and convergence tolerances. These values are semantic policy identity, not runtime defaults.

## Forecast xP reconciliation

A joint scenario stream is not valid simply because action-level metrics look stable. At the broadest usable convergence checkpoint, each declared player/Gameweek scenario expectation is reconciled to canonical sealed `Forecast` expected points.

For each player/Gameweek:

1. calculate the exact weighted scenario mean;
2. calculate the canonical Forecast expected points, summing all fixture rows in that Gameweek;
3. apply the policy's explicit absolute tolerance;
4. when required, compare residual deviation with the governed sampling-error allowance using weighted variance and effective sample size.

A missing Forecast player/Gameweek target is an error, not zero. A material mismatch makes robustness `INCONCLUSIVE`.

The scenario system may model dependence around the marginal Forecast, but it may not silently rewrite canonical xP.

## Convergence

A report can be `CONVERGED` only when all of the following hold:

- at least two governed nested checkpoints are available;
- the compared action set is identical across checkpoints;
- mean ranking is stable;
- lower-CVaR ranking is stable;
- lower-tail ranking is stable;
- each action's mean change is within policy tolerance;
- each action's CVaR change is within policy tolerance;
- each action's tail-quantile change is within policy tolerance;
- Forecast xP reconciliation succeeds;
- no blocker remains.

Otherwise the report is `INCONCLUSIVE` and carries explicit blockers.

`INCONCLUSIVE` reports expose **no** robustness-preferred action and no robustness EV-regret value. This prevents unstable diagnostics from being consumed as selection authority.

## Expected value remains the anchor

The DecisionEngine's selected action is the EV anchor. Slice 9 may identify a tail-preferred action only after convergence, and only inside the exact `max_ev_regret_tolerance` encoded by the scenario policy.

An action outside that regret band is excluded from robustness preference even if it has a better sample CVaR. Therefore robustness cannot silently change the optimization objective from expected FPL points to CVaR.

Any future production policy that uses robustness to alter an executable action must be separately empirically qualified and must make that bounded substitution rule explicit in its semantic policy identity.

## No-hindsight policy and generator governance

A scenario generator declares:

- valid season(s);
- training cutoff;
- first-available timestamp;
- maximum horizon;
- immutable parameter artifacts;
- qualification state and evidence.

It cannot be used for a historical forecast if its training data or availability occurred after that forecast cutoff.

A convergence policy similarly has a first-available timestamp. A later policy cannot be retroactively applied to make a historical decision look certified.

Production use additionally requires the generator and convergence policy to be registered, `QUALIFIED`, backed by readable qualification artifacts, and selected as their registered champions. There is intentionally no default champion.

## Persistence and replay

`ScenarioSet` and `RobustnessReport` are stored as immutable content-addressed JSON artifacts. Replay:

- parses integers/booleans strictly;
- reconstructs typed constitutional objects;
- recalculates semantic identities;
- rejects declared-ID mismatches;
- reopens every referenced scenario source artifact.

A missing or corrupt source artifact invalidates replay. Normalized stored JSON cannot launder missing worker provenance.

## Failure behavior

The following do not become successful robustness evidence:

- only 256 available scenarios when a broader checkpoint is required;
- changed rankings or metrics outside tolerance;
- missing player/Gameweek Forecast coverage;
- xP expectation mismatch;
- missing/corrupt source artifact;
- suspended/unqualified generator in production;
- suspended/unqualified convergence policy in production;
- generator or policy unavailable at the historical forecast cutoff;
- runtime RNG generation below the seal;
- inference of correlation from Slice 7 marginal scenario labels.

These states are errors or `INCONCLUSIVE`, never an improvised fallback.

## PR #66 / V1 migration rule

V1 robustness/CVaR/scenario code and PR #66 are reference material only. Slice 9 retained useful lessons—broader convergence certification, typed failure/limit semantics, and certificate reuse only when structured evidence proves equivalent-or-broader coverage—but did not import V1 scenario implementations as production authority.

## Current production boundary

Slice 9 can prove software contracts and produce shadow robustness evidence. It does not make Apex `ready_to_act=true` or `safe_to_act=true`.

Production recommendation authority still requires the later independent-assurance, learning/qualification, shadow-production and cutover slices, together with qualified forecast, decision and scenario policies on one sealed current surface.
