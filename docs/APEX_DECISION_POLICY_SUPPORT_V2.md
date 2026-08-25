# Apex V2 DecisionPolicy Support Contracts

## Purpose

A production `DecisionPolicy` is not defined only by a policy name and a horizon. Its continuation value, chip option value, price semantics, candidate-universe semantics, numeric policy and tie-break semantics all change which FPL action is optimal.

Those semantics therefore cannot be represented by arbitrary artifact IDs whose only admission check is that some bytes exist.

This contract makes the support surface typed, content-addressed and replayable before empirical qualification is allowed to authorize a receding-horizon policy.

## Authority boundary

Typed support artifacts are **mechanism evidence**, not production qualification.

A valid continuation/chip/price/candidate artifact does not make a `DecisionPolicy` production-safe. Production still requires:

1. the exact policy to be registered;
2. the exact policy to be the configured champion;
3. a replay-valid typed empirical qualification for `PO-DECISION-POLICY-QUALIFICATION-001`;
4. the qualification to bind the stable prequalification identity of the exact policy;
5. the policy and every support artifact to be available at the decision cutoff;
6. all other production release proofs and backend authority to pass.

Synthetic qualification fixtures used by tests are mechanism tests only and must never be copied into production registries.

## Content identity

Each support object serializes to canonical semantic JSON. Its semantic ID is the SHA-256 content identity of those exact bytes, and the `ArtifactStore` artifact ID must equal that semantic ID.

Loading is strict:

- bytes must pass content-integrity verification;
- JSON must be canonical;
- `schema_name` and `schema_version` must match the expected support type;
- the reconstructed typed object must reproduce the requested artifact ID;
- explicit `as_of` checks use only caller-supplied time and never the wall clock.

An arbitrary existing SHA is therefore not a valid policy support artifact.

## Continuation-value policy

V1 support mode is `EXACT_GAMEWEEK_WEIGHTS_ZERO_TERMINAL`.

The artifact binds:

- season;
- horizon length;
- first-availability timestamp;
- one exact rational weight per Gameweek in the declared horizon;
- exact terminal value;
- support mode.

Fail-closed rules:

- horizon is at least two Gameweeks;
- current-Gameweek weight is exactly 1;
- all weights are non-negative;
- at least one future Gameweek has positive weight, so a receding policy cannot secretly collapse to a one-GW tactical policy;
- terminal value is exactly zero in V1, so an opaque terminal penalty cannot be smuggled into the objective.

A richer terminal-value model requires a new explicit support mode and its own qualification; it cannot silently change V1 semantics.

## Chip-option policy

V1 support mode is `EXACT_TERMINAL_RESERVE`.

The artifact explicitly enumerates an exact non-negative rational option value for all four long-lived FPL chips:

- Triple Captain;
- Bench Boost;
- Wildcard;
- Free Hit.

The artifact also binds season, horizon and first availability. The registry requires its horizon to equal the parent `DecisionPolicy` horizon.

These exact values are policy semantics, not claims that the values are empirically correct. Their adequacy is part of empirical DecisionPolicy qualification.

## Price policy

V1 mode is `OFFICIAL_CURRENT_ONLY`.

Production policy may use the exact Official current FPL price/selling-resource state already sealed into V2. It may not silently introduce speculative future price forecasts through an opaque support artifact.

A future predictive price model requires a new typed mode, explicit provenance and qualification.

## Candidate policy

V1 mode is `FULL_OFFICIAL`.

The production receding-horizon policy support contract therefore cannot hide an undocumented shortlist or prefilter inside an artifact ID. Any future candidate-reduction policy must be a new explicit typed mode with exactness/expansion evidence.

## Numeric policy

V2 decision numerics currently have one supported identity:

`decision-rational-v1`

That identity is now part of `DecisionPolicy` semantic identity. The sealed reference-solver request independently requires both embedded `DecisionInput` and embedded `DecisionPolicy` to declare the same canonical numeric policy.

This closes a forged-request path where a caller could otherwise label the DecisionInput with different numeric semantics while the worker executed exact-rational arithmetic.

## Tie-break semantics

The currently implemented canonical tie-break is:

`lexicographic-official-id-v1`

Both tactical and receding `DecisionPolicy` objects fail closed if another tie-break identity is requested. A future tie-break can be added only when executable semantics and independent parity coverage exist for it.

## Registry replay

For every receding policy, `DecisionPolicyRegistry.verify_policy_artifacts` replays all four typed supports even in non-production verification. It then requires:

- every support season to equal the policy season;
- continuation horizon to equal policy horizon;
- chip-option horizon to equal policy horizon;
- every support to have been available no later than the parent policy's own `first_available_at`.

Production verification additionally requires the exact registered champion, explicit `as_of`, policy availability and replay-valid typed empirical qualification.

## What this branch does not claim

This support layer does **not** implement the receding-horizon optimisation engine itself.

The isolated reference solver certified in PR #82 remains tactical-current-Gameweek only. A production receding-horizon engine and corresponding independent parity/qualification surface are still required before a DecisionPolicy champion can be justified.

`config/decision_policies_v2.yaml` remains empty. No champion is fabricated. Actual production cutover remains withheld, and Slice 14 remains blocked until a genuine `PUBLISHED` V2 release exists.
