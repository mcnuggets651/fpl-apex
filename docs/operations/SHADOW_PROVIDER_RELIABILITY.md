# Apex V2 External Shadow Provider Reliability

## Incident

Production run `33469824474-1` on 2026-09-01 was actionable but reported `DEGRADED` certification. The immutable governance bundle proves the serving path was healthy and AIrsenal remained the sole serving provider H1-H8.

The initial diagnosis that Dastan failed was wrong. Dastan was `HEALTHY` and `QUALIFIED` for H1. The actual warnings were:

- PITCHSIDE: `INCOMPLETE`; the public bundle predated the Apex attempt and lacked target-GW FORECAST coverage for 50 current Official FPL element IDs.
- OpenFPL: `ERROR`; `acquisition/providers/openfpl.csv` did not exist.

## Root causes

### Dastan

No incident. Dastan is generated inside each Apex production attempt by `scripts/acquire_dastan_shadow.py`; that execution model satisfies the frozen engine's attempt-local provenance rule. Do not add retries or fallbacks merely to address run `33469824474`: there was nothing to repair.

### PITCHSIDE

PITCHSIDE is an external, periodically published public snapshot. The frozen V2 acquisition layer applies an additional generic warning whenever `surface.generated_at < production_attempt_started_at`. That is valid for per-attempt workers such as AIrsenal/Dastan, but it is not a valid freshness definition for an immutable external publication. A PITCHSIDE snapshot can be recent, pre-deadline, internally consistent and less than the configured 18-hour TTL while still predating the Apex attempt.

The same run also exposed a genuine upstream coverage gap: the PITCHSIDE target-GW matrix omitted 50 Official elements. Apex correctly refused to call that surface qualified.

Apex cannot make an upstream model forecast newly-added players, and it must never synthesize xP or rewrite the upstream `generated_utc` timestamp. The permanent boundary therefore treats PITCHSIDE as an **external diagnostic**, with its own transport/freshness/coverage report, rather than as part of production certification.

### OpenFPL

The missing CSV was not a transient outage. Frozen V2 config expected `acquisition/providers/openfpl.csv`, but no production step creates that file. More importantly, the governed OpenFPL policy explicitly forbids constructing a current-rules derivative until at least **10 completed 2026/27 exact-rule gameweeks** exist. The pinned upstream reference uses legacy scoring and its fitted weights may not be reused.

Therefore `provider export missing` was a category error: frozen V2 was treating an intentionally unavailable research model as a failed live provider.

## Permanent contract

`PITCHSIDE` and `OpenFPL` are external diagnostics in frozen Apex V2:

- `serve_authorized = false`
- `production_influence = NONE`
- no blending
- no voting
- no auto-promotion
- no manager credentials
- no solver access
- no mutation of Official state

The operations controller derives a runtime config from the frozen config and removes only these two external diagnostics from the production qualification matrix. It fails closed if either source ever becomes serving-authorized or if the AIrsenal H1-H8 champion invariant changes.

Dastan and Apex Proprietary remain attempt-local SHADOW providers in the frozen qualification matrix. AIrsenal remains the only serving champion.

This is an operations-layer classification repair. The frozen engine SHA remains unchanged.

## PITCHSIDE health contract

The external diagnostic monitor:

1. reads Official public bootstrap/fixtures;
2. fetches `meta.json`, `xp.json`, and `players.json` with bounded retry;
3. retries only transient failures (`408`, `429`, `5xx`, connection errors);
4. does not retry permanent `4xx` errors;
5. double-reads `meta.json` to reject a bundle that changed during acquisition;
6. records SHA-256 for each upstream object;
7. derives the target GW from Official FPL;
8. requires the target GW in the xP matrix;
9. maps PITCHSIDE FPL player codes back to current Official element IDs;
10. reports exact missing target-GW forecast IDs and coverage ratio;
11. uses the governed 18-hour age limit;
12. does **not** require the upstream forecast to have been generated after the Apex attempt began;
13. writes reports atomically.

Health states are `HEALTHY`, `INCOMPLETE`, `STALE`, or `ERROR`. These states are diagnostic only and never alter the canonical decision.

## OpenFPL readiness contract

Frozen V2 reports OpenFPL readiness separately from production. The monitor observes the current upstream 2026/27 gameweek directory, counts only upstream gameweek files that are also marked `finished=true` and `data_checked=true` by Official FPL and are strictly before the Official target GW, and advances automatically from `DEFERRED_BY_GOVERNANCE` to `READY_FOR_SHADOW_BUILD` when the governed floor is met. It records:

- the pinned OpenFPL reference identity;
- the pinned 2026/27 history identity;
- the governed 10-GW minimum;
- current-rules-only training labels;
- prohibition on legacy fitted weights;
- `serve_authorized=false`;
- `production_influence=NONE`.

Crossing the 10-GW history floor does **not** auto-build or auto-enable OpenFPL. It only changes the readiness state to `READY_FOR_SHADOW_BUILD`, permitting a separately governed current-rules shadow build and validation. Promotion remains impossible without an explicit architecture decision. The health record includes the observed gameweek list and a SHA-256 manifest of the upstream file identities so the transition is auditable.

## Failure semantics

External diagnostic failure must be visible but must not create a false production incident. Production certification answers whether the serving/attempt-local decision system is trustworthy. External diagnostic health answers whether optional independent references are currently useful.

A real serving defect still fails closed. This change does not relax Official hash parity, manager-state verification, AIrsenal freshness, solver legality, immutable publication, orphan detection, or authentication controls.

## Regression coverage

`tests/test_apex_v2_shadow_provider_ops.py` covers:

- exact externalisation set;
- AIrsenal H1-H8 invariants;
- refusal to externalise a serving-authorized provider;
- OpenFPL governance-deferred classification and automatic transition at the 10-GW floor;
- PITCHSIDE pre-attempt-but-fresh regression;
- incomplete target-GW coverage;
- transient retry and permanent 4xx behaviour;
- atomic output.

The production workflow contract additionally asserts that the frozen engine SHA is unchanged and the runtime config is derived only through the operations controller.
