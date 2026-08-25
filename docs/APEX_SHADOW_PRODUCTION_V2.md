# Apex V2 Shadow Production

## Purpose

Slice 12 rehearses the V2 release path before production cutover.

A shadow run exercises immutable evidence, `AssuranceCase`, derived `ReleaseCertificate`, `ReleaseRecord`, release CAS semantics and offline replay while remaining structurally non-actionable.

A shadow PASS is **not** production eligibility and is **not** permission to publish a team.

## Authority boundary

Shadow production consumes already-sealed V2 evidence. It does not fetch football data, retrain models, run V1 services or invent missing proof claims.

The production release registry is exposed to the shadow runner through the read-only `CurrentReleaseReader` protocol. The runner records the production current pointer before and after the rehearsal and the immutable `ShadowProductionReport` rejects any claim of success if those values differ.

Shadow writes use a distinct `FileSystemReleaseRegistry` root/namespace supplied by the caller. Only that shadow registry receives `append` and `compare_and_swap_current` calls.

## Release semantics

The supplied `AssuranceCase` derives its `ReleaseCertificate` from the supplied proof obligations.

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

The resulting `ShadowProductionReport` is stored under canonical content identity. Replay:

1. verifies the report envelope and semantic ID;
2. reconstructs the strict typed report;
3. re-verifies every retained source artifact.

Missing or corrupt evidence therefore invalidates a historical shadow PASS rather than leaving a stale green boolean behind.

## CAS behavior

Shadow current pointers use the existing release-registry compare-and-swap operation. A stale shadow writer fails with `CompareAndSwapConflict` and does not receive a successful report.

The production current pointer is read only. Concurrent production movement makes the rehearsal non-certifiable because `production_pointer_before != production_pointer_after`.

## Failure semantics

The runner fails closed for:

- missing/corrupt manifest;
- missing/corrupt AssuranceCase artifact evidence;
- stale shadow CAS;
- production-pointer movement during the rehearsal;
- malformed or tampered stored shadow reports;
- missing/corrupt replay source evidence.

An AssuranceCase that is internally valid but lacks a mandatory proof does not crash. It creates a non-actionable `WITHHELD` shadow release whose blockers come from the derived ReleaseCertificate.

## Cutover boundary

Slice 12 does **not** change production authority.

Production cutover remains Slice 13 and must be an explicit, separately certified change. Slice 13 must consume evidence that V2 shadow production passed; it cannot reinterpret a shadow pointer as the production current pointer.
