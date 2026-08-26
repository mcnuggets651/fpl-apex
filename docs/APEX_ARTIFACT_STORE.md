# Apex Artifact Store

## Status

V2 production-control-plane contract. Runtime recommendation state is not source-authoritative.

A deployable provider-neutral PostgreSQL adapter now exists in the #85 engineering slice, but **no real production PostgreSQL deployment or production operational qualification is claimed**. Production remains withheld.

## Invariant

Git contains source, tests, configuration, schemas, documentation and qualified manifests. Live recommendations, answer contexts, planning bundles, source captures and production-run reports are runtime artifacts.

`ArtifactStore` is the stable port. Runtime objects are immutable and content-addressed by SHA-256. The filesystem adapter in `src/apex_fpl/control/artifact_store.py` is a reference/local-recovery adapter and is structurally forbidden from production qualification.

## Implementations

### Filesystem reference adapter

The filesystem adapter remains useful for local replay, tests and recovery tooling. It cannot become production merely because a caller supplies non-empty evidence IDs or green capability booleans.

### PostgreSQL deployable adapter

`PostgresArtifactStore` stores immutable content-addressed objects in PostgreSQL and verifies SHA-256 identity on read. Its logical backend identity is persisted inside the database and survives connection/credential/hostname changes and fresh-adapter reopen.

`PostgresReleaseRegistry` uses the same persisted logical control-plane identity model, immutable ReleaseRecord history and transactional compare-and-swap for the current pointer.

Database bootstrap is explicit. Immutable backend-identity, artifact and release rows are protected from UPDATE/DELETE by database triggers. Production runtime roles are intended to operate with DML-only permissions after administrative bootstrap.

PostgreSQL is the first deployable implementation, not a constitutional vendor lock-in. The domain ports remain provider-neutral.

## Two-plane production qualification

A shared backend does not become production-qualified from a fresh-connection probe alone.

Plane A is live mechanical evidence for stable identity, shared visibility, integrity, immutable replay, forged-ID rejection and atomic CAS.

Plane B is retained deployment/operations evidence for properties that cannot be proved by a short-lived probe:

- long-term retention;
- access-control policy;
- credential separation;
- backup success;
- restore success;
- disaster recovery;
- availability;
- geographic durability.

Production qualification binds both planes to the exact ArtifactStore identity, ReleaseRegistry identity and production qualification scope. The two role-specific qualification artifacts each bind the exact mechanical probe and the same deployment evidence artifact. Replay re-derives qualification from retained evidence; caller-authored booleans cannot promote a backend.

See `docs/APEX_BACKEND_OPERATIONAL_QUALIFICATION_V2.md` for the complete contract.

## CI is not production evidence

Apex CI starts a digest-pinned PostgreSQL 17.11 service and exercises real cross-connection behavior. This proves adapter/control-plane mechanics only.

A GitHub Actions PostgreSQL service does **not** prove retention, production access controls, credential separation, backups, restore, disaster recovery, availability or geographic persistence and therefore is never real production backend qualification.

## Required production properties

The real backend must provide and retain evidence for:

- immutable object writes;
- SHA-256 content identity and verification;
- durable retention independent of a single process/Actions run;
- access control and production credential separation;
- backup and verified restore;
- disaster-recovery capability;
- availability evidence;
- geographic durability where required by the production deployment policy;
- portable export/recovery;
- schema/version metadata in manifests;
- corruption detection;
- stale-writer-safe atomic current-pointer CAS;
- immutable release history;
- no mutation of repository history as a publication mechanism.

## Failure semantics

Artifact integrity mismatch is fatal. Missing runtime artifacts are explicit absence, never reconstructed from a stale tracked `*_latest` file. Missing/incomplete/corrupt/mismatched operational qualification evidence withholds production rather than degrading to a caller-authored assertion.
