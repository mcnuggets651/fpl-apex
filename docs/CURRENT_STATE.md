# Apex FPL — Current State

Operating authority: [`APEX_OPERATING_MANUAL.md`](APEX_OPERATING_MANUAL.md).

**Last updated:** 2026-08-26

## Production status

- Repository: `mcnuggets651/fpl-apex`.
- Production branch remains `main`.
- V2 work remains in reviewed draft PRs; green CI on an open branch is engineering evidence only, never production authority.
- **Actual V2 production cutover remains WITHHELD.** No Apex V2 recommendation may be exposed until an exact current `PUBLISHED` release, publication authorization, schema-v2 production planning bundle, mandatory proofs, qualified champions and exact qualified shared backend identities all replay successfully inside their validity window.
- No production forecast-model, DecisionPolicy, scenario/dependence or planning reference-solver champion is fabricated by repository configuration.
- `config/experiments_v2.yaml` still contains no retrospective qualification shortcut. Empirical production qualification remains prospective and no-hindsight.

## Certified parent — PR #84 exact receding-horizon planner

Branch: `v2/receding-horizon-planner`  
PR: #84 — **draft/open/unmerged, engineering certified**  
Certified head: `e535fc289a3e6885f34bf6ca45f6ebd42a84241c`

Exact same-head certification evidence:

- Apex CI run `32972587860`: SUCCESS.
- Full suite: **795 passed**.
- Ruff, upstream pin checks and governance consistency: PASS.
- Immutable runtime image: `sha256:97d537255ec225581890f79c4538e7fa14ace61c4c62b16c597e7c2dc0255cec`.
- Build manifest: `sha256:badb2067ddfee219b54d533995e6f42ba6c118059f53451d7f30f10262d42bf6`.
- Dependency lock digest: `sha256:ffa1141cab8b1bfa9e89ab69fa97dfe2e256ed7526314d88d4056cdb1a3b87f0`.
- SBOM artifact: `sha256:a6ec5ccc252cb6636a98f383770abd14df1928ce3a133a2503d45776671e0f3f`.
- Provenance artifact: `sha256:c4d98c3c8550212f01a2adca8803836a3214d49869e473eb5878a0cb1fe54635`.
- Build-evidence artifact ID `9609030571`, ZIP digest `sha256:4b706c4a4a8feb116d9aa89837a7772d57178759718833bb752dba67d5b577f5`; the downloaded ZIP digest reconciled exactly.
- V2 Shadow Production run `32972587878`: SUCCESS, 15/15 shadow contract tests + Ruff.

PR #84 is therefore the certified engineering parent for subsequent V2 slices, but it remains unmerged pending explicit approval.

## PR #85 — durable PostgreSQL production backend

Branch: `v2/postgres-production-backend`  
PR: #85 — **draft/open/unmerged**

PR #85 has now been genuinely restacked onto certified #84. The restack commit uses GitHub's own conflict-resolved merge tree and has certified #84 as an ancestor; comparison to `e535fc2...` reports `behind_by=0`.

### Implemented backend mechanism

- Provider-neutral production backend ports.
- Persisted logical PostgreSQL backend identities independent of DSN/host/credential labels.
- Explicit PostgreSQL control-plane bootstrap.
- Immutable SHA-256 `PostgresArtifactStore` with cross-connection replay/integrity verification.
- Immutable `PostgresReleaseRegistry` with verified ReleaseRecord identity and transactional stale-writer-safe CAS.
- Digest-pinned PostgreSQL 17.11 integration service in Apex CI.
- Focused backend-contract CI job plus the complete Apex suite.

### Two-plane production qualification

Backend qualification is deliberately split so database integration tests cannot impersonate real operational durability.

**Plane A — mechanical behavior** proves only what fresh adapters can observe:

- stable persisted backend identity;
- shared cross-connection visibility;
- SHA-256 integrity;
- immutable ReleaseRecord replay;
- forged-release identity rejection;
- stale-writer CAS conflict; and
- successful CAS transition.

`derive_backend_qualification_from_probes()` returns only `VerifiedBackendMechanicalQualification`; it cannot directly authorize production.

**Plane B — retained deployment/operations evidence** requires complete typed evidence for:

1. retention;
2. access control;
3. credential separation;
4. backup;
5. restore;
6. disaster recovery;
7. availability; and
8. geographic durability.

Plane B must be `environment_class=PRODUCTION`, complete, PASS, exact-backend-bound, exact-scope-bound and backed by retained source artifacts. TEST evidence, incomplete evidence, random bytes, copied evidence from another backend/scope or corrupt evidence fails closed.

The two planes are joined through role-specific content-addressed production qualification bindings. Both bindings must reference the same Plane-B evidence. Cutover and answer-authority replay independently re-derive the qualification; caller-authored green booleans cannot override retained evidence.

Production cutover/answer-authority code is verifier-only for Plane B. Generic evidence-authoring helpers are administrative/test utilities and are not imported or invoked by runtime publication paths. Synthetic helpers live under `tests/` and are explicitly mechanism-only.

## PR #85 certification state

The restacked branch is undergoing final candidate maintenance. Before final certification the candidate must include:

- executable two-plane qualification traceability;
- genuinely focused backend fast-fail CI;
- final Project Brain/governance wording; and
- fresh exact-head Apex CI plus V2 Shadow Production.

No earlier #85 run may certify the final candidate after these changes.

## Remaining production blockers after PR #85 engineering certification

### 1. Real deployed shared backend evidence

PR #85 implements a deployable PostgreSQL backend and qualification mechanism, but **does not deploy or qualify a real production database**. GitHub Actions PostgreSQL proves Plane A mechanics only. Real retained Plane-B operational evidence for the actual deployed backend identities is still required.

### 2. Real production champions

Forecast model, DecisionPolicy, scenario/dependence and planning reference-solver production champions remain absent until their exact qualification contracts pass. Synthetic test certificates are never production evidence.

### 3. Prospective empirical evidence

Required empirical production proofs must remain predeclared/no-hindsight. Already-known historical outcomes cannot be relabelled retrospectively as production qualification evidence.

### 4. Production cutover

Cutover remains WITHHELD until one exact schema-v2 `ProductionPlanningBundle`, exact runtime, exact qualified champions, complete AssuranceCase, exact qualified backend identities and time-bounded publication authorization all replay successfully.

### 5. Slice 14

Slice 14 remains blocked until a genuine current `PUBLISHED` V2 production release exists. PR #66 remains archaeology/regression evidence only.

## Next sequence

1. Freeze the final #85 candidate on certified #84 ancestry.
2. Pass the focused PostgreSQL/two-plane backend contract gate.
3. Pass full same-head Apex CI, inspect exact test count, runtime digest, SBOM/provenance and uploaded build evidence.
4. Pass same-head V2 Shadow Production.
5. Keep #85 draft/open/unmerged until explicit merge approval.
6. Separately deploy a real shared production PostgreSQL control plane and collect genuine Plane-B operational evidence; do not treat CI as deployment qualification.
7. Complete prospective champion/empirical qualification work.
8. Assemble/replay the genuine production bundle and cut over only if the constitutional authority chain passes.
9. Begin Slice 14 only after a real current PUBLISHED V2 release exists.

## User-facing FPL boundary

Until the V2 production authority chain passes, do not invent or manually select a squad and label it Apex V2. A user-facing Apex recommendation must come from the canonical current production authority contract; otherwise report the blocker explicitly.
