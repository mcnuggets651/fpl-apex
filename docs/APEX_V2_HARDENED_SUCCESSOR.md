# Apex V2 Hardened Successor — Trust, Replay and Promotion Contract

## Status

This document defines the promotion contract for the immutable successor to engine
`99cc7b51b0cff45462b567084cb1844cfe0a456f`. It does not authorize promotion by
itself. Production remains pinned to the old immutable SHA until every gate below is
satisfied by a separate control-plane change.

PR #90 remains frozen and unmerged. Audit PR #120 remains evidence only and must not
be merged. AIrsenal remains the sole serving champion for H1-H8 unless a future,
separately governed model-promotion decision changes that constitution.

## Security and correctness invariants

A production recommendation is actionable only if all of the following are true:

1. **Official truth is coherent.** Player IDs, stable codes, teams, positions, prices,
   fixtures and gameweeks are internally consistent and bound to one Official FPL
   snapshot hash.
2. **Forecasts are snapshot-bound and clock-bound.** A serving surface names that
   exact Official hash, has one coherent row per required player/horizon, and H1/H2…
   map to the actual next Official deadlines.
3. **Serving authority is explicit.** Boolean authorization fields are typed booleans;
   shadows cannot become serving providers through truthiness, missing configuration,
   voting or blending.
4. **The acquisition snapshot is content addressed.** The snapshot ID is recomputed
   from the canonical manifest; every file is a canonical relative path with verified
   SHA-256 and byte length.
5. **Solve is offline and rechecks time-sensitive state.** Provider freshness is
   evaluated again at solve time against the sealed SLA. A stale champion cannot be
   actioned merely because it was fresh at acquisition.
6. **FPL economics are replayed independently.** Certification verifies legal squad,
   XI, bench, transfer ownership, exact sell prices, affordability, free transfers,
   hits and mode-specific state rather than trusting optimizer metadata.
7. **Evidence is chronological and attributable.** Future-dated, expired, malformed or
   untrusted hard evidence cannot authorize a decision.
8. **Publication is a second trust boundary.** It reopens the content-addressed
   snapshot, reconstructs serving identity and canonical forecast, then performs an
   independent deterministic offline solve. Recommendation, certification, optimizer
   result, contingency state, evidence interpretation and runtime serving health must
   reproduce before any publication artifacts are constructed.
9. **Persistence is fail-closed.** Failed mutable release attempts are cleaned up;
   immutable publication is never reported successful after partial upload or replay
   disagreement.
10. **Every serving-critical invariant has permanent regression evidence.** Example,
    property/metamorphic, golden-replay and targeted mutation tests are all required.

## Threat model

The hardened core assumes external inputs can be stale, malformed, internally
inconsistent or adversarial. It specifically defends against:

- provider rows from a different Official snapshot;
- forged or unknown fixtures and gameweeks;
- YAML/JSON truthiness attacks (`"false"` becoming true);
- non-finite freshness values (`NaN`, `Infinity`);
- snapshot path traversal and manifest/hash rewriting;
- stale-at-solve provider state;
- unaffordable or ownership-incoherent transfer metadata;
- incorrect hit/free-transfer state;
- future, expired or malformed evidence;
- post-solve mutation of certification or the actual FPL recommendation;
- partial release failure leaving an apparently valid mutable record.

The core does **not** treat a shadow model as trusted simply because it predicts well.
Serving promotion is an operations/governance event requiring prospective evidence.

## Test classes required for promotion

### Contract tests
All V2 example/regression tests, architecture-boundary checks and Ruff must pass.

### Property and metamorphic tests
State transitions and probabilities are tested over generated input spaces. Snapshot
identity must be insertion-order invariant and content-sensitive; FPL free-transfer
state remains bounded; autosub weights remain probabilities; captain/vice selection
matches its exhaustive objective; mechanics EV decomposes exactly.

### Golden replay corpus
At least two sanitized synthetic sealed snapshots are replayed with fixed clocks:

- an initial-squad decision;
- a multi-horizon transfer decision.

Both the content-addressed snapshot ID and complete DecisionBundle digest are frozen.
Unexplained drift is a release blocker.

### Mutation gate
CI deliberately removes critical protections in temporary source copies. The regression
suite must kill every registered mutant. A surviving security mutant blocks promotion.

### Coverage floor
Branch-aware coverage is recorded for all V2 tests. Critical serving modules have
per-file floors and the complete V2 package has a global floor. Coverage may increase
without governance work; reducing a floor requires an explicit reviewed change.

## Determinism contract

Given the same sealed snapshot, explicit evaluation clock and engine commit, solve must
produce the same semantic DecisionBundle. Publication intentionally performs a second
solve. Runner-local metadata that is not a decision input may differ, but the following
must not:

- system decision;
- certification state/actionability/reasons;
- serving provider map;
- contingency qualification;
- optimizer decision result;
- evidence interpretation;
- runtime serving health.

## Model-quality governance

Correctness hardening is separate from forecast improvement. AIrsenal remains champion
while challengers run prospectively and immutably. Forecast metrics and realized FPL
decision-edge metrics are both evidence; neither can rewrite historical forecasts.
Automatic promotion, retrospective cherry-picking, provider voting and silent blending
remain prohibited.

Any future model change must define before the deadline:

- forecast target and horizon coverage;
- calibration metrics (xP error, minutes error, appearance/start/60 calibration);
- decision-edge experiment class;
- minimum prospective sample/evidence threshold;
- rollback and shadow period;
- explicit new serving constitution if authority changes.

## Operational promotion checklist

A successor SHA may replace production only after:

- [ ] full repository CI is green on the clean candidate;
- [ ] V2 contract and architecture checks are green;
- [ ] critical branch-coverage floors pass;
- [ ] property/metamorphic suite passes;
- [ ] golden replay digests pass;
- [ ] all registered critical mutants are killed;
- [ ] no audit-only workflow/tooling exists in the candidate core;
- [ ] current-main control-plane reachability is audited;
- [ ] a non-serving canary runs the successor without publication authority;
- [ ] canary divergences from the serving core are classified and accepted/rejected;
- [ ] dependency/provenance evidence is sealed;
- [ ] the final production-pin PR changes only the explicitly reviewed control plane;
- [ ] PR #90 and PR #120 remain unmerged;
- [ ] post-promotion production smoke/replay confirms the new immutable SHA.

A failed gate means **no promotion**. Fix the cause, add a regression and repeat the
gate; never weaken the gate merely to make the candidate pass.
