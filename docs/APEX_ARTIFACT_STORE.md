# Apex Artifact Store

## Status

Slice 0 contract. Runtime recommendation state is no longer source-authoritative.

## Invariant

Git contains source, tests, configuration, schemas, documentation and qualified manifests. Live recommendations, answer contexts, decision bundles, source captures and production-run reports are runtime artifacts.

`ArtifactStore` is the stable port. Runtime objects are immutable and content-addressed by SHA-256. The filesystem adapter in `src/apex_fpl/control/artifact_store.py` is a reference/local-recovery adapter, not the final durable production backend.

## Slice 0 backend

`Apex Unified` stages a sealed workflow packet into the filesystem adapter and uploads that packet as a GitHub Actions artifact. This is intentionally labelled `transitional_ci_artifact`.

GitHub Actions artifacts are **not** accepted as the only long-term V2 store. A later slice must select and qualify a durable shared backend using operational evidence (retention, access control, availability, portability, integrity, cost and recovery characteristics) before production cutover.

## Required production properties

The eventual backend must provide:

- immutable object writes;
- SHA-256 content identity and verification;
- durable retention independent of a single Actions run;
- access control and production credential separation;
- portable export/recovery;
- schema/version metadata in manifests;
- corruption detection;
- no mutation of repository history as a publication mechanism.

## Failure semantics

Artifact integrity mismatch is fatal. Missing runtime artifacts are explicit absence, never reconstructed from a stale tracked `*_latest` file.
