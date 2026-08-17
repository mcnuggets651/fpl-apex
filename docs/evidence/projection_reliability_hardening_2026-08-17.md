# Projection reliability hardening — 17 August 2026

## Why the frozen architecture was reopened

The first post-freeze production recommendation exposed a reproducible contract defect, not a subjective dislike of a player. A low-sample Apex attacking-rate forecast could remain a large outlier versus both Official FPL and AIrsenal while retaining the full configured Apex expert weight. Generic `projection_confidence` was calculated only after the canonical expected-value mean and therefore could not protect the decision surface.

The production regression was identity-independent in structure: Apex approximately 7.93 GW1 xP versus Official FPL 1.50 and AIrsenal 1.03, with weak underlying attacking-rate evidence, blended to approximately 4.68 canonical xP because the direct Apex vote retained its full 51.11% nominal weight. The optimiser then correctly maximised an unreliable surface.

A second class of defect was also reproducible: prior-season starts described a role at the player's old club but were carried into the new club without a depth-chart reset. Goalkeeper transfers are the clearest high-impact case because only one starting slot exists. Preseason role evidence also treated early tour matches and the final rehearsal equally even though FPL Core friendlies contain parseable match dates.

## Non-goals

This change does **not**:

- ban or special-case any player;
- reward nailedness as a separate optimisation objective;
- multiply xP by generic minutes confidence;
- retune the configured 26.67% Official / 51.11% Apex / 22.22% AIrsenal nominal weights;
- reactivate the retired Bayesian shrinkage model;
- suppress a high-reliability differentiated Apex view merely because another model disagrees;
- add an invented possession multiplier for defensive contributions.

## Permanent contracts

### 1. Component-specific Apex reliability

The transparent projection now emits `attack_rate_reliability`, `defensive_rate_reliability`, and `apex_model_reliability`.

An ordinary or mature attacking rate remains fully reliable. A rate becomes evidence-thin only when it is above the mature same-position reference and is backed by fewer than 270 prior Premier League minutes. Understat agreement and measured preseason attacking evidence can rebuild that reliability. A zero-prior-minute player with an ordinary rate is not penalised.

### 2. Independent-disagreement gate

The configured Apex weight remains the ceiling. The direct Apex vote is attenuated only when:

1. `apex_model_reliability < 1`;
2. at least two usable independent experts exist on the row; and
3. Apex lies materially outside their envelope.

A confirmed GW1 conflict is allowed to carry into later horizon rows where Official FPL no longer publishes expected points, but only while Apex remains on the same side of the remaining independent consensus. All effective weights, consensus bounds, margins, conflict direction and inherited status are published as projection columns.

This is deliberately narrower than confidence weighting: weak minutes confidence by itself cannot lower canonical EV.

### 3. Recency-aware preseason role evidence

FPL Core friendly `match_id` values include the match date. Role evidence now uses a ten-day exponential half-life so a final rehearsal can outweigh an early tour start. Attacking-rate sample totals remain based on measured minutes and are not recency-inflated.

### 4. Transfer-aware role bridge

Stable `player_code` plus season-specific `team_code` identifies a genuine club change. Prior starts/minutes are then regressed toward a neutral depth-chart prior until current preseason evidence establishes the new role. Goalkeepers receive the strongest reset. Explicit attributable deadline overrides still replace the statistical prior.

### 5. Transfer-aware defensive contributions

For a club-changed player, historical defensive-contribution rate is shrunk toward a mature same-position reference according to current-role evidence. This avoids assuming that an old tactical environment transfers one-for-one while also avoiding an unvalidated possession coefficient.

## Regression requirements

The change is not promotable unless tests prove all of the following:

- a 7.93 / 1.50 / 1.03 low-reliability Apex outlier is materially attenuated;
- the same conflict propagates to later GWs while the remaining independent expert confirms its direction;
- a high-reliability Apex outlier retains the full nominal vote;
- low reliability without independent disagreement leaves canonical EV unchanged;
- the final preseason rehearsal outweighs a distant early tour start for role inference;
- a transferred incumbent goalkeeper cannot inherit an old-club near-certain start without current evidence;
- a verified current override can establish that transferred goalkeeper as starter;
- cross-season team identity is unambiguous and auditable;
- a transferred historical defensive-contribution outlier shrinks toward the same-position reference;
- existing expert decomposition, set-piece, minutes, solver, strategy and fail-closed contracts remain green.

## Promotion gate

This PR must pass the complete governed CI/audit suite and then produce a fresh live decision artifact. Promotion is based on contract correctness and the resulting projection diagnostics, not on whether a preferred player appears in the XV. No merge without explicit user approval.
