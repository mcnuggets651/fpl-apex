# Apex V2 Production Cutover — Slice 13

Slice 13 is the only explicit transition by which V2 may become the current production authority. It does not infer production readiness from framework health, a green shadow run, a branch name, a caller-supplied backend label or a standalone boolean.

## Two distinct proof phases

`PO-PRODUCTION-CUTOVER-001` is a REQUIRED **pre-publication mechanism proof**. It certifies that the exact executing build, identified by immutable build/runtime provenance, passed the Slice 13 contract tests that enforce certificate-only publication, actual-backend identity binding, reference-filesystem exclusion, time-bounded authority, replay and stale-writer-safe CAS.

A specific runtime attempt then produces `ProductionPublicationAuthorization`, an immutable `ReleaseRecord`, a CAS result and `ProductionCutoverReport`. Those artifacts audit what happened in that attempt. They do not circularly authorize the same attempt that creates them.

## Publication sequence

1. Resolve one exact season / entry / Gameweek release scope and exact executing runtime identity.
2. Verify the immutable ArtifactManifest and every retained artifact referenced by the AssuranceCase, including the exact-build Slice 13 mechanism-certification evidence.
3. Validate that the supplied proof registry contains the complete constitutional REQUIRED production proof surface. A narrowed or downgraded proof set is invalid input.
4. Derive the ReleaseCertificate from the machine-readable AssuranceCase. There is no second readiness gate that can override this result.
5. Verify retained production control-plane qualification evidence **and bind it to the actual adapters being used**. ArtifactStore and ReleaseRegistry expose stable backend identities; those identities must exactly match the qualification. Both backends must be durable, shared, immutable/history-preserving and CAS-capable. `FileSystemArtifactStore` and `FileSystemReleaseRegistry` carry explicit `apex.reference.*` backend identities and remain structurally non-production even if a caller supplies green capability booleans.
6. Validate an explicit timezone-aware `created_at` and non-null `valid_until` with `valid_until > created_at`.
7. Seal a `ProductionPublicationAuthorization` containing the exact scope, bundle/world/runtime/manifest identities, exact `created_at`/`valid_until`, AssuranceCase snapshot, proof-registry snapshot, ReleaseCertificate result and the content identity of the backend-qualification snapshot.
8. Construct exactly one immutable `ReleaseRecord` bound to that authorization artifact and the identical validity window. Its `ready_to_act` and `safe_to_act` fields are derived from authorization; they are never caller inputs.
9. If authorization is WITHHELD, retain immutable attempt evidence and require the production current pointer to remain unchanged.
10. If authorization is eligible, append and replay the exact immutable PUBLISHED ReleaseRecord, then compare-and-swap the current pointer from the observed predecessor to that exact release ID. A stale writer fails closed.
11. The answer surface resolves only the current PUBLISHED V2 ReleaseRecord and independently replays its publication authorization, manifest and authorization-bound backend qualification. The backend identities in that qualification must match the actual store/registry serving the answer. The caller supplies an explicit timezone-aware `as_of`; hidden wall-clock time is forbidden. Authority is withheld before `created_at` and at or after `valid_until`.
12. Immediately before returning authority, re-read the current pointer. Concurrent pointer drift withholds the answer rather than exposing the superseded release.
13. Persist the `ProductionCutoverReport` and CAS lineage as post-attempt immutable audit evidence.

A PUBLISHED-looking ReleaseRecord is not sufficient authority. V1 records, shadow records, CERTIFIED-only records, forged `ready=true` records, reference-filesystem publication attempts, cross-backend authorization replay, missing or mismatched backend identities, missing/expired validity windows, corrupt authorization, corrupt manifests, pointer drift and stale publication attempts are non-actionable.

## Status versus actionability

`WITHHELD` is a successful fail-closed outcome when evidence is incomplete. It never moves the production pointer and derives both readiness flags as false.

`PUBLISHED` is possible only after a blocker-free ReleaseCertificate, complete proof lineage, identity-bound qualified production backend evidence, a valid explicit publication horizon and successful exact CAS. Only then do `ready_to_act` and `safe_to_act` derive true, and only until the retained `valid_until` horizon.

A green Slice 13 code/test implementation is therefore not itself a production cutover. Runtime publication remains correctly WITHHELD until the real production evidence is qualified.

## Current 2026/27 cutover blockers

The repository deliberately does not fabricate default production authorities. At Slice 13 implementation time the registered V2 forecast-model, DecisionPolicy, scenario/dependence, reference-solver and learning-policy champion slots are empty. In addition, the filesystem ArtifactStore and ReleaseRegistry are reference/local adapters; retained qualification evidence for a real durable shared production control plane is required before live cutover.

Those conditions are expected to keep a real production AssuranceCase/cutover WITHHELD until genuine qualification work supplies evidence. Tests use synthetic non-reference durable backend doubles only to prove the transition algorithm; their synthetic identities and evidence are never production qualification artifacts.

## Immutable history and rollback

Publication never mutates an existing ReleaseRecord. Historical releases and their source artifacts remain addressable by content identity. A later release becomes current through another CAS transition. Rollback means a governed current-pointer transition to an already retained release only if that release is still valid under the applicable policy and proof surface; it does not rewrite historical bytes or resurrect an expired authorization.

## Relationship to Slice 12 and Slice 14

Slice 12 proves that the real release contract can be rehearsed while structurally non-actionable and while the production current pointer remains read-only. A shadow PASS is not cutover permission.

Slice 14 may begin only after a genuine Slice 13 production cutover is certified. Slice 14 then removes or disables competing V1 production writers and obsolete parallel readiness/publication paths while preserving historical replay evidence. Until that successful cutover exists, legacy production authority must not be removed prematurely.

## Machine-enforced surfaces

- `src/apex_fpl/core/production.py`
- `src/apex_fpl/control/artifact_store.py`
- `src/apex_fpl/control/production_backend_qualification.py`
- `src/apex_fpl/control/production_cutover.py`
- `src/apex_fpl/core/production_authority.py`
- `src/apex_fpl/control/production_authority.py`
- `src/apex_fpl/control/release_registry.py`
- `config/proof_obligations.yaml` — `PO-PRODUCTION-CUTOVER-001`
- `config/requirements.yaml` — `REQ-V2-PRODUCTION-CUTOVER`
- `docs/APEX_INVARIANTS.md`
- `tests/test_v2_production_cutover.py`
- `tests/test_v2_production_authority.py`
- `tests/test_v2_production_architecture.py`
- `tests/test_v2_production_traceability.py`
