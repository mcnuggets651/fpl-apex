# Apex V2 Backend Operational Qualification

## Status

This document defines the production backend qualification contract introduced by the durable PostgreSQL control-plane slice. It does **not** claim that a real production PostgreSQL deployment currently exists or is qualified.

Production remains withheld until a real shared backend and its real operational evidence are retained and replay successfully.

## Constitutional rule

Apex backend qualification has two independent evidence planes. Neither plane may impersonate the other.

### Plane A — live mechanical qualification

Plane A is machine-verifiable and provider-neutral. It runs against fresh/reopened adapters and proves only behavior that can honestly be observed during the qualification run:

- persisted stable backend identity;
- cross-connection ArtifactStore visibility;
- exact SHA-256 content replay and integrity verification;
- cross-connection ReleaseRegistry visibility;
- immutable ReleaseRecord replay;
- rejection of forged ReleaseRecord identity;
- stale-writer compare-and-swap conflict;
- successful compare-and-swap transition;
- final current-pointer identity.

`derive_backend_qualification_from_probes()` produces a `VerifiedBackendMechanicalQualification`. It deliberately does **not** produce a production-qualified `ProductionBackendQualification`.

A PostgreSQL service started inside GitHub Actions can satisfy Plane A. That remains mechanism/integration evidence only.

### Plane B — retained deployment/operations qualification

Plane B covers properties that a fresh database probe cannot truthfully establish. Production qualification requires retained typed observations covering **all** of:

1. `RETENTION`
2. `ACCESS_CONTROL`
3. `CREDENTIAL_SEPARATION`
4. `BACKUP`
5. `RESTORE`
6. `DISASTER_RECOVERY`
7. `AVAILABILITY`
8. `GEOGRAPHIC_DURABILITY`

Each observation binds:

- exact ArtifactStore backend identity;
- exact ReleaseRegistry backend identity;
- exact production qualification scope;
- concrete deployment identity;
- evidence kind;
- issuer;
- observation time;
- PASS/FAIL outcome;
- one or more retained source artifacts whose integrity is verified.

The aggregate `BackendDeploymentQualificationEvidence` is content-addressed. It is supported only for `environment_class=PRODUCTION`, complete required coverage and all PASS outcomes. A `TEST` environment can exercise the mechanism but cannot qualify production.

A random byte artifact is not deployment evidence. Missing source artifacts, mismatched scope/backend identity, duplicated evidence kinds, incomplete coverage, corrupt observations or TEST-class evidence fail closed.

## Composite production binding

The two artifact IDs already carried by `ProductionBackendQualification` are role-specific **production qualification bindings**, not raw probe artifacts.

Each binding commits to:

- role (`ARTIFACT_STORE` or `RELEASE_REGISTRY`);
- exact backend identity;
- exact qualification scope;
- exact Plane A mechanical evidence artifact;
- the exact shared Plane B deployment qualification artifact.

Both bindings must reference the same deployment evidence. Stored replay loads the composite bindings, replays both underlying probes, replays every deployment observation/source artifact, checks exact identity/scope agreement and re-derives the qualification booleans. Caller-authored booleans cannot override that derivation.

This prevents:

- random bytes as qualification;
- green-boolean laundering;
- artifact/registry evidence copied from another backend;
- deployment evidence copied from another scope or deployment;
- corrupt or missing evidence payloads;
- filesystem reference-adapter promotion;
- treating CI PostgreSQL as real operational qualification.

## PostgreSQL implementation

`PostgresArtifactStore` and `PostgresReleaseRegistry` are the first provider-neutral deployable adapters.

The logical backend identity is persisted inside PostgreSQL and is independent of DSN, hostname, credentials or environment labels. Reopening through a fresh connection must return the same identity.

Database bootstrap creates immutable backend-identity, artifact and release rows plus the mutable current-pointer table. UPDATE/DELETE protection on immutable rows is enforced by database triggers. Current-pointer publication uses transactional compare-and-swap.

PostgreSQL is an implementation choice, not a constitutional vendor lock-in. The ports remain provider-neutral.

## CI contract

Apex CI uses a digest-pinned PostgreSQL 17.11 service. Two jobs are intentional:

- `backend-contract`: fast fail for PostgreSQL adapters, two-plane qualification, cutover/authority replay and Ruff on the backend surface;
- `test`: the complete Apex suite plus Ruff, upstream verification, governance consistency, immutable image build, SBOM and provenance.

The focused job is a correctness/feedback gate, not production deployment evidence and not a substitute for full same-head certification.

## Real-production requirement

Before a real cutover, the operator must supply actual retained Plane B evidence from the real deployed shared backend. Synthetic test fixtures are explicitly mechanism-only and must never be registered as production evidence.

No code path in this slice deploys a production database, invents operational evidence, creates model/policy/scenario/solver champions or publishes an Apex recommendation.
