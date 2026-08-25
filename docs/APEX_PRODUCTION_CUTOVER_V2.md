# Apex V2 Production Cutover — Slice 13

Slice 13 is the only explicit transition by which V2 may become the current production authority. It does not infer production readiness from framework health, a green shadow run, a branch name, or a standalone boolean.

## Publication sequence

1. Resolve one exact season / entry / Gameweek release scope.
2. Verify the immutable ArtifactManifest and every retained artifact referenced by the AssuranceCase.
3. Validate that the supplied proof registry contains the complete constitutional REQUIRED production proof surface. A narrowed or downgraded proof set is invalid input.
4. Derive the ReleaseCertificate from the machine-readable AssuranceCase. There is no second readiness gate that can override this result.
5. Verify retained production control-plane qualification evidence. The ArtifactStore and ReleaseRegistry must be durable, shared, immutable/history-preserving and CAS-capable. The filesystem adapters remain reference/local implementations and are not production-qualified merely because their contract tests pass.
6. Seal a `ProductionPublicationAuthorization` containing the exact scope, bundle/world/runtime/manifest identities, AssuranceCase snapshot, proof-registry snapshot, ReleaseCertificate result and backend-qualification lineage.
7. Construct exactly one immutable `ReleaseRecord` bound to that authorization artifact. Its `ready_to_act` and `safe_to_act` fields are derived from the authorization result; they are never caller inputs.
8. If authorization is WITHHELD, retain immutable attempt evidence and require the production current pointer to remain unchanged.
9. If authorization is eligible, append and replay the exact immutable PUBLISHED ReleaseRecord, then compare-and-swap the current pointer from the observed predecessor to that exact release ID. A stale writer fails closed.
10. The answer surface resolves only the current PUBLISHED V2 ReleaseRecord and independently replays its publication authorization and manifest before exposing its bundle identity.

A PUBLISHED-looking ReleaseRecord is not sufficient authority. V1 records, shadow records, CERTIFIED-only records, forged `ready=true` records, corrupt/missing authorization, corrupt manifests and stale publication attempts are non-actionable.

## Status versus actionability

`WITHHELD` is a successful fail-closed outcome when evidence is incomplete. It never moves the production pointer and derives both readiness flags as false.

`PUBLISHED` is possible only after a blocker-free ReleaseCertificate, complete proof lineage, qualified production backend evidence and successful exact CAS. Only then do `ready_to_act` and `safe_to_act` derive true.

A green Slice 13 code/test implementation is therefore not itself a production cutover. Runtime publication remains correctly WITHHELD until the real production evidence is qualified.

## Current 2026/27 cutover blockers

The repository deliberately does not fabricate default production authorities. At Slice 13 implementation time the registered V2 forecast-model, DecisionPolicy, scenario/dependence, reference-solver and learning-policy champion slots are empty. In addition, the filesystem ArtifactStore and ReleaseRegistry are reference/local adapters; retained qualification evidence for a durable shared production control plane is required before live cutover.

Those conditions are expected to keep a real production AssuranceCase/cutover WITHHELD until genuine qualification work supplies evidence. Tests may use synthetic qualified objects only to prove the transition algorithm; synthetic evidence is never a production qualification artifact.

## Immutable history and rollback

Publication never mutates an existing ReleaseRecord. Historical releases and their source artifacts remain addressable by content identity. A later release becomes current through another CAS transition. Rollback means publishing a new governed current-pointer transition to an already retained valid release only under the applicable release policy; it does not rewrite historical bytes.

## Relationship to Slice 12 and Slice 14

Slice 12 proves that the real release contract can be rehearsed while structurally non-actionable and while the production current pointer remains read-only. A shadow PASS is not cutover permission.

Slice 14 may begin only after a genuine Slice 13 production cutover is certified. Slice 14 then removes or disables competing V1 production writers and obsolete parallel readiness/publication paths while preserving historical replay evidence. Until that successful cutover exists, legacy production authority must not be removed prematurely.

## Machine-enforced surfaces

- `src/apex_fpl/core/production.py`
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
