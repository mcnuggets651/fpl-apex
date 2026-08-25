# Apex V2 Shadow Production

## Purpose

Slice 12 rehearses the V2 release path before production cutover.

A shadow run exercises immutable evidence, `AssuranceCase`, derived `ReleaseCertificate`, `ReleaseRecord`, release CAS semantics and offline replay while remaining structurally non-actionable.

A shadow PASS is **not** production eligibility and is **not** permission to publish a team.

## Authority boundary

Shadow production consumes already-sealed V2 evidence. It does not fetch football data, retrain models, run V1 services or invent missing proof claims.

The production release registry is exposed to the shadow runner through the read-only `CurrentReleaseReader` protocol. The runner records the production current pointer before and after the rehearsal and the immutable `ShadowProductionReport` rejects any claim of success if those values differ.

Shadow writes use a distinct `FileSystemReleaseRegistry` root/namespace supplied by the caller. Only that shadow registry receives `append` and `compare_and_swap_current` calls.

## Independent reference-solver boundary

A replay-valid algorithmic qualification for an isolated reference-solver worker is independent assurance evidence only. It does not elevate a shadow release, mutate the production current pointer, set `ready_to_act`/`safe_to_act`, or create user-facing recommendation authority.

Reference-solver qualification and shadow production therefore fail closed independently:

- shadow rehearsal cannot substitute for a missing qualified reference-solver champion;
- a qualified worker cannot substitute for a production `ReleaseCertificate` or publication authorization;
- a tactical current-Gameweek worker cannot certify a receding-horizon production DecisionPolicy merely because its tactical parity corpus passes;
- any solver authorization consumed by publication-grade assurance must still replay its exact worker, registry and qualification evidence under the production release path.

This separation prevents engineering evidence from being promoted into production authority by implication.

## Release semantics

The supplied `AssuranceCase` derives its `ReleaseCertificate` from the supplied proof obligations. Proof obligations are canonicalized by `proof_id` before both derivation and sealing, and duplicate proof IDs fail before any release is staged.

- eligible certificate -> shadow `ReleaseRecord.status=CERTIFIED`;
- ineligible certificate -> shadow `ReleaseRecord.status=WITHHELD`.

In **both** cases:

- `ready_to_act=false`;
- `safe_to_act=false`;
- no production current pointer is changed;
- no user-facing recommendation authority is created.

This deliberately separates "the V2 release path works" from "V2 has been cut over to production".

## Artifact integrity

Before shadow execution:

- the artifact manifest must verify in `ArtifactStore`;
- every artifact ID attached to an `AssuranceClaim` must verify.

The runner additionally seals two content-addressed policy snapshots:

1. the exact `AssuranceCase` plus its derived semantic identity;
2. the exact canonical `ProofObligation` set used to derive the release certificate.

Both snapshot artifacts are mandatory `ShadowProductionReport` lineage. The resulting report is stored under canonical content identity. Replay:

1. verifies the report envelope and semantic ID;
2. reconstructs the strict typed report;
3. re-verifies every retained source artifact;
4. reconstructs the exact retained `AssuranceCase`;
5. reconstructs the exact retained proof-obligation set;
6. independently re-derives the `ReleaseCertificate`;
7. requires its AssuranceCase ID, PASS/FAIL status and blocker tuple to match the stored report exactly.

This prevents a historical PASS from surviving a changed release policy or from being explained only by a stale green boolean. Missing or corrupt evidence invalidates the replay.

## CAS behavior

Shadow current pointers use the existing release-registry compare-and-swap operation. A stale shadow writer fails with `CompareAndSwapConflict` and does not receive a successful report.

The production current pointer is read only. Concurrent production movement makes the rehearsal non-certifiable because `production_pointer_before != production_pointer_after`.

## Failure semantics

The runner fails closed for:

- missing/corrupt manifest;
- missing/corrupt AssuranceCase artifact evidence;
- duplicate proof IDs;
- missing/corrupt retained AssuranceCase or proof-policy snapshot;
- replayed ReleaseCertificate disagreement;
- stale shadow CAS;
- production-pointer movement during the rehearsal;
- malformed or tampered stored shadow reports;
- missing/corrupt replay source evidence.

An AssuranceCase that is internally valid but lacks a mandatory proof does not crash. It creates a non-actionable `WITHHELD` shadow release whose blockers come from the derived ReleaseCertificate.

## CI contract

`.github/workflows/v2-shadow-production.yml` uses the same frozen dependency installation path as Apex CI, runs every `tests/test_v2_shadow_*.py` contract/adversarial/traceability test and runs Ruff over the entire Slice 12 surface. Constitutional proof/requirement/invariant changes also trigger this workflow.

## Cutover boundary

Slice 12 does **not** change production authority.

Production cutover remains Slice 13 and must be an explicit, separately certified change. Slice 13 must consume evidence that V2 shadow production passed; it cannot reinterpret a shadow pointer as the production current pointer.
