# Apex FPL — Current State

Operating authority: [`APEX_OPERATING_MANUAL.md`](APEX_OPERATING_MANUAL.md).

**Last updated:** 2026-08-26

## Production status

- Repository: `mcnuggets651/fpl-apex`.
- Production branch remains `main`.
- V2 work remains in reviewed draft PRs; green CI on an open branch is engineering evidence only, never production authority.
- **Actual V2 production cutover remains WITHHELD.** No Apex V2 recommendation may be exposed until an exact current `PUBLISHED` release, publication authorization, schema-v2 production planning bundle, mandatory proofs, qualified champions and exact qualified shared backend identities all replay successfully inside their validity window.
- No production forecast-model, DecisionPolicy, scenario/dependence or planning reference-solver champion is fabricated by repository configuration.
- Empirical production qualification remains prospective/no-hindsight. Already-known historical outcomes cannot be relabelled as prospective qualification evidence.

## Certified engineering lineage

### PR #84 — exact receding-horizon planner

Branch: `v2/receding-horizon-planner`  
PR: #84 — **draft/open/unmerged, engineering certified**  
Certified head: `e535fc289a3e6885f34bf6ca45f6ebd42a84241c`

Same-head evidence included 795 passing tests, Ruff/upstream/governance PASS, immutable build evidence and successful V2 Shadow Production. It remains an engineering parent only.

### PR #85 — durable PostgreSQL production backend

Branch: `v2/postgres-production-backend`  
PR: #85 — **draft/open/unmerged, engineering certified**  
Certified head: `5be756e677b6f0b876f616319a943485c5875d68`

Final exact same-head certification:

- V2 Shadow Production run `32982434975`: SUCCESS, 15/15 tests + Ruff.
- Apex CI run `32982435016`: SUCCESS.
- Backend-contract job: 21/21 focused PostgreSQL/two-plane qualification/traceability tests + Ruff.
- Comprehensive suite: **817 passed in 2294.78s**.
- Full Ruff, all 8 upstream pins and governance consistency: PASS.
- Runtime image: `sha256:3cd52e05c79ccf5cf15f3fd24256af4e2df900850fce7666ad366045d1eeebac`.
- Dependency lock: `sha256:d4b23096b48c80162a123b781f00904dc0851785a198ae1f1570f176418f936a`.
- Build-manifest identity: `sha256:e5eeeb32eb710a9fc9de48782c4c26a55fb4926ffb07745390b628aeed530f5f`.
- SBOM: `sha256:9ad264fb3702cadbde7a5f87563118d18b7f84a79bbd9f7685ae6a0daf553fb2`.
- Provenance: `sha256:481a06fe31e5e57534e5211fb9afd285b0e36f02f86c5497946ebba2e948f08e` bound to exact certified source SHA.
- Build-evidence artifact `9612924946`; GitHub ZIP digest and independently downloaded ZIP both equal `sha256:7ed5c94264820d79715c0560b933b9843c15f3092db480982e5cdcc83dcda49d`.

PR #85 implements the deployable shared control-plane mechanism and replayable two-plane qualification contract. It does **not** assert that a real production database has been deployed or operationally qualified.

## PR #86 — prospective empirical operations plane

Branch: `v2/prospective-empirical-operations`  
PR: #86 — **draft/open/unmerged; implementation complete, certification pending**  
Base: exact engineering-certified PR #85 head `5be756e677b6f0b876f616319a943485c5875d68`.

### Implemented

- Fail-closed `ProductionBackendRuntime` using `APEX_PRODUCTION_POSTGRES_DSN` and optional schema.
- No local-filesystem production fallback.
- Persisted backend identity output without exposing DSN credentials.
- Immutable SHADOW forecast-model candidate materialization with verified parameter lineage and reviewable exact registry row.
- Immutable SHADOW receding-horizon DecisionPolicy candidate materialization with replay-valid typed support artifacts.
- Operator-recorded candidate availability time; caller cannot backdate it.
- Prospective experiment declaration using execution-time UTC; caller cannot supply `declared_at`, and declaration after the evaluation window begins fails closed.
- Post-window result sealing using execution-time UTC; caller cannot supply `evaluated_at`, and premature results fail closed.
- Replay-derived empirical qualification from exact retained candidate/definition/registry/result lineage.
- Explicit QUALIFIED-candidate materialization only from a SUPPORTED certificate for the exact proof/subject/season.
- Candidate qualification returns `review_required=true` and `champion_changed=false`; champion admission remains a separate reviewed immutable operation.
- Separate `apex-v2` operator CLI for backend identity, immutable evidence sealing, candidate materialization, experiment declaration/result, qualification derivation and qualified-candidate proposals.
- Focused CI coverage for production runtime and prospective empirical operations.
- V2 Shadow path coverage includes the new authority surfaces, with PR concurrency cancellation so obsolete shadow audits are cancelled.
- Dedicated operator runbook: `docs/APEX_PROSPECTIVE_EMPIRICAL_OPERATIONS_V2.md`.
- Project Brain, V2 architecture, changelog and decision register updated; D035 records the permanent operator chronology/promotion boundary.

### Required before #86 engineering certification

1. Freeze the final branch head after this governance refresh.
2. Pass the new focused backend/operations fast-fail CI on that exact head.
3. Pass the complete same-head Apex pytest suite, full Ruff, upstream pin checks and governance consistency.
4. Build the immutable runtime and reconcile the same-head SBOM/provenance/build-manifest artifact.
5. Pass same-head V2 Shadow Production.
6. Record certification evidence in PR metadata only; do not change the certified branch merely to record the result.

## Remaining production blockers after #86 engineering certification

### 1. Real deployed shared backend evidence

The PostgreSQL mechanism exists, but a genuine production control plane still needs deployment plus retained Plane-B evidence for retention, access control, credential separation, backup, restore, disaster recovery, availability and geographic durability bound to the exact deployed backend identities.

### 2. Future prospective empirical outcomes

The operator path can now predeclare and retain future experiments safely. It cannot manufacture the future observations required to qualify production subjects. Known historical outcomes remain unsuitable as prospective production evidence.

### 3. Reviewed production champions

Forecast model, DecisionPolicy, scenario/dependence and planning reference-solver champions remain absent until their exact qualifications pass and separate reviewed admission/promotion mechanisms authorize them. A QUALIFIED candidate is not automatically the champion.

### 4. Production cutover

Cutover remains WITHHELD until one exact current schema-v2 `ProductionPlanningBundle`, exact runtime, exact qualified champions, complete AssuranceCase, exact qualified deployed backend identities and time-bounded publication authorization all replay successfully.

### 5. Slice 14

Slice 14 remains blocked until a genuine current `PUBLISHED` V2 production release exists. PR #66 remains archaeology/regression evidence only.

## Next sequence

1. Certify PR #86 on one exact frozen head.
2. Keep #86 draft/open/unmerged until explicit merge approval.
3. Deploy the real shared PostgreSQL control plane outside CI and collect genuine operational evidence; do not treat CI as deployment qualification.
4. Materialize actual SHADOW candidates and predeclare future qualification experiments before their evaluation windows.
5. Retain future outcomes after the windows, derive certificates and propose QUALIFIED candidates only where evidence is SUPPORTED.
6. Perform separate reviewed champion admissions; never auto-promote from qualification.
7. Assemble/replay the genuine production planning bundle and cut over only if the complete constitutional authority chain passes.
8. Begin Slice 14 only after a real current PUBLISHED V2 release exists.

## User-facing FPL boundary

Until the V2 production authority chain passes, do not invent or manually select a squad and label it Apex V2. A user-facing Apex recommendation must come from the canonical current production authority contract; otherwise report the blocker explicitly.
