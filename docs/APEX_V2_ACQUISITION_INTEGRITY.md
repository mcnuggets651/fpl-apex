# Apex V2 — Acquisition Transaction Integrity

## Purpose

Apex V2 acquisition is a trust boundary. A snapshot may be solved or published only if the bytes that drove acquisition decisions are the same bytes sealed into the immutable snapshot.

This contract exists to prevent time-of-check/time-of-use drift between configuration parsing, evidence collection, provider qualification and final snapshot creation.

## Transaction invariant

For every decision-driving local input, acquisition follows **capture → operate → verify → seal**:

1. **Capture once.** Read the source bytes into memory before they are interpreted.
2. **Operate on the capture.** Parsing/adapters consume an immutable temporary copy of those captured bytes rather than re-reading the live source path.
3. **Verify the live source did not change.** Before the transaction is allowed to freeze, the original path must still contain the captured bytes. Mutation or disappearance is a fatal, machine-classified acquisition error.
4. **Seal the capture.** The frozen snapshot contains the exact captured bytes and their cryptographic provenance, never a later live re-read.

The transaction must never claim provenance for bytes that were not the bytes used to make the acquisition decision.

## Configuration

`config/apex_v2.yaml` is captured before `ApexConfig` is constructed. The configuration is parsed from a temporary file containing the captured bytes.

The live configuration path is checked immediately after parsing and again immediately before freeze. Any change aborts acquisition with the stable stage `config_integrity`.

`run.json` and snapshot metadata record the SHA-256 of the captured configuration, and `config.yaml` contains those exact bytes.

## External evidence

When external evidence is required:

- the evidence-source YAML is captured before collection;
- collection receives an immutable temporary copy of that source configuration;
- the live source configuration is checked after collection and again before freeze;
- the final acquisition manifest binds the exact canonical evidence records with `records_sha256`;
- the manifest binds the exact evidence-source bytes with `source_config_sha256`;
- record count is retained as a diagnostic but is never treated as a content-integrity proof;
- the snapshot seals the source configuration, normalized evidence, canonical raw evidence-record payload and the strengthened acquisition manifest;
- `run.json` and snapshot metadata repeat the evidence-record and source-configuration hashes.

A same-count evidence substitution therefore fails. A source-config substitution therefore fails. A required manifest without a payload hash therefore fails.

## Provider projections

Each provider export is captured before its adapter runs. The adapter receives a temporary file containing the captured bytes; it does not interpret the live provider path.

After adapter parsing and qualification, Apex verifies that the original provider file still matches the capture. Mutation or disappearance aborts with `provider_integrity`.

The snapshot's `provider_raw/*` file is built from the captured bytes. It is not a second read of the live provider path.

This closes both ordinary TOCTOU drift and an ABA-style mutation where the live file changes while the adapter is running.

## Official FPL authority sandwich

Provider/evidence local integrity does not replace the Official FPL authority sandwich.

Apex still re-fetches Official FPL at the final authority anchor and compares it with the pre-provider Official seal when one was supplied. A mismatch aborts the attempt. The target Gameweek is derived only after this final reanchor.

The frozen run records both the pre-provider and final Official hashes and whether the authority remained stable.

## Failure semantics

Integrity failures are fatal and stable-classified:

- `config_integrity` — configuration changed/disappeared or could not be captured safely;
- `evidence_integrity` — source configuration or evidence payload drifted;
- `provider_integrity` — provider bytes changed/disappeared during qualification;
- `official_reanchor` — Official FPL authority changed across the acquisition sandwich.

These failures must not be downgraded to warnings for a serving provider or required evidence source.

## Assurance requirements

The V2 test suite must retain adversarial regressions for at least:

- same-count evidence payload substitution;
- required evidence-source configuration sealing;
- provider mutation during adapter execution;
- configuration mutation after parse;
- explicit manager-credential opt-in combinations;
- no-future-deadline failure;
- every provider adapter dispatch operating on captured bytes;
- missing/broken optional providers remaining non-serving diagnostics;
- provider forecast predating the current attempt degrading qualification.

`src/apex/runtime/acquire.py` is a serving-critical module and is subject to an explicit per-file coverage floor in the V2 assurance workflow.

## Promotion rule

A successor core is not eligible for production promotion merely because ordinary model tests pass. The exact successor SHA must also pass:

- locked-environment installation and dependency verification;
- full V2 branch-coverage suite including this acquisition contract;
- critical per-file coverage floors;
- semantic mutation sentinels;
- architecture boundary checks;
- lint;
- deterministic semantic replay goldens;
- provenance and CycloneDX SBOM generation;
- read-only exact-head readiness/canary verification.

Production authority remains unchanged until the complete proof chain is green.
