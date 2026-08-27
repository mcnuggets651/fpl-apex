# Apex V2 Production Cutover — Slice 13

Slice 13 is the only explicit transition by which V2 may become the current production authority. It does not infer production readiness from framework health, a green shadow run, a branch name, a caller-supplied backend label or a standalone boolean.

## Two distinct proof phases

`PO-PRODUCTION-CUTOVER-001` is a REQUIRED **pre-publication mechanism proof**. It certifies that the exact executing build, identified by immutable build/runtime provenance, passed the production-control-plane contract tests that enforce certificate-only publication, constitutional proof-class pinning, typed empirical qualification admission, schema-v2 planning lineage replay, qualified reference-solver parity, actual-backend identity binding, reference-filesystem exclusion, time-bounded authority, replay and stale-writer-safe CAS.

A specific runtime attempt then produces `ProductionPublicationAuthorization`, an immutable `ReleaseRecord`, a CAS result and `ProductionCutoverReport`. Those artifacts audit what happened in that attempt. They do not circularly authorize the same attempt that creates them.

## Schema-v2 planning lineage before publication

Authoritative production cutover accepts only `ProductionPlanningBundle` schema v2. Legacy schema-v1 tactical bundles remain replayable historical/mechanism evidence but cannot move the V2 production pointer.

The schema-v2 bundle is content-addressed and binds the exact retained:

- current `ManagerState` and self-addressing manager-state artifact;
- `RuleSet` and self-addressing RuleSet artifact;
- `Forecast` and exact `ForecastModelArtifact`;
- qualified receding-horizon `DecisionPolicy` and its continuation-value, chip-option-value, price and candidate-policy support artifacts;
- full-Official `CandidateUniverse`;
- replay-derived `RecedingHorizonDecisionResult` / `PlanningResultId`;
- `ScenarioSet`; and
- converged `RobustnessReport`.

Bundle replay re-executes the planning lineage from retained current manager truth and retained RuleSet. Production rejects a planning result unless its solver status is `OPTIMAL`, search is complete, its best bound reconciles, its exact gap is zero and every retained hypothetical state/trajectory transition replays. `SOLVER_LIMIT`, missing state/rules bytes, tactical-only policy semantics, non-full candidate scope, non-converged robustness or swapped model/policy/world lineage fail closed.

See `docs/APEX_RECEDING_HORIZON_PLANNER_V2.md`.

## Replayed champion authority before publication

Qualification proves eligibility, not production selection. Before publication Apex must load one immutable `ProductionChampionGeneration` that already existed at the explicit release time. Forecast-model authority is accepted only when the retained model-registry generation points to promotion evidence whose exact candidate/incumbent evaluation reports, comparison report and qualified champion learning-policy registry independently re-derive `PROMOTE`. DecisionPolicy, scenario-generator and scenario-policy authority each require an exact retained reviewed admission whose typed empirical qualification was valid at the generation authorization time. Parent generations are recursively replayed at the child authorization time. Naive or future review/authorization timestamps fail closed.

The generation must exact-match the forecast model, DecisionPolicy, `ScenarioSet.scenario_generator_id` and `RobustnessReport.scenario_policy_id` in the already replayed schema-v2 planning bundle. `ProductionPublicationAuthorization` schema v2 binds the exact champion-generation artifact. Cutover and answer authority independently replay that artifact; runtime publication code may verify it but cannot issue admissions, promotions or champion generations. See `docs/APEX_CHAMPION_AUTHORITY_V2.md`.

## Typed empirical admission before publication

Mandatory empirical proof IDs are not satisfied merely because their AssuranceClaims cite immutable artifacts. The production proof-class contract pins every mandatory proof ID to its constitutional `ProofClass`; callers cannot relabel an empirical proof as formal or algorithmic.

Each satisfying empirical production claim must contain a replay-valid `EmpiricalQualificationCertificate` derived from one predeclared registered experiment and retained result evidence. The certificate must reconcile the release season and exact proof ID, and the AssuranceClaim must explicitly bind the certificate's stable subject identity and experiment identity. Production empirical proof IDs also have canonical release subject kinds, so lower-level qualifications cannot impersonate composite claims:

- forecast qualification → `apex.forecast-model`
- DecisionPolicy qualification → `apex.decision-policy`
- scenario convergence → `apex.scenario-convergence`
- model evaluation → `apex.model-evaluation`
- model promotion → `apex.model-promotion`

Scenario-generator, scenario-policy and learning-policy registry qualification use separate internal qualification IDs. A qualified generator does not prove a realised scenario stream converged; a qualified learning policy does not prove a model evaluation passed. Reference-solver parity remains an algorithmic certificate, not empirical qualification.

The qualification certificate is independently replayed at the release's explicit `created_at`. It is unavailable before its retained result availability and expired at `valid_until`. Random artifacts, certificates for another proof/subject/season, future evidence and expired certificates fail closed. See `docs/APEX_EMPIRICAL_QUALIFICATION_V2.md`.

## Qualified planning reference-solver parity

`PO-REFERENCE-SOLVER-PARITY-001` is a mandatory algorithmic proof on the production planning path. Generic artifact existence cannot satisfy it.

A satisfying claim must bind the exact schema-v2 bundle's `PlanningResultId` to a replay-derived `PlanningReferenceSolverCertificate` and replay-valid `ReferenceSolverAuthorization`. Production independently verifies that:

- retained solver request/output bytes re-derive the certificate;
- request identities match the exact DecisionInput, full CandidateUniverse and DecisionPolicy used by the planning bundle;
- the independent worker returned `OPTIMAL`, complete, exact zero-gap search;
- the independent best horizon objective equals the Apex planning selection objective;
- the exact selected current root action and entire selected trajectory identities match;
- the tie-break policy is the exact implemented policy;
- the retained registry snapshot names the exact certificate worker as champion;
- the champion code artifact and planning-v2 algorithmic qualification replay successfully;
- the worker qualification covers the exact release season and horizon; and
- authorization cutoff equals the exact Forecast feature cutoff.

The planning qualification corpus derives its required coverage from retained cases. It must actually exercise full-Official search, multi-Gameweek objective, free-transfer banking, nontrivial transfer finance, non-zero terminal chip reserve, Triple Captain, Bench Boost, Wildcard persistence, Free Hit reversal, root-action parity, trajectory parity and zero-gap completion. Caller-authored coverage labels cannot promote a worker.

A random algorithmic artifact, a valid certificate for another planning result, an unauthorized certificate, a tactical-v1 worker/certificate, a non-champion worker, missing qualification, solver limit/error, objective disagreement or trajectory disagreement fails production parity.

The same parity chain is replayed when `ProductionPublicationAuthorization` is later loaded. Evidence that was valid only at initial write time is insufficient.

## Publication sequence

1. Resolve one exact season / entry / Gameweek release scope and exact executing runtime identity.
2. Verify the immutable ArtifactManifest and every retained artifact referenced by the AssuranceCase, including the exact-build production-control-plane mechanism-certification evidence.
3. Validate that the supplied proof registry contains the complete constitutional REQUIRED production proof surface, and that every mandatory proof retains its pinned constitutional ProofClass. A narrowed, downgraded or reclassified proof set is invalid input.
4. Load and independently replay the exact schema-v2 `ProductionPlanningBundle`; reconcile season, entry, Gameweek, GlobalWorld and every retained decision-lineage identity; reject tactical schema v1 as production authority. Then load the exact point-in-time `ProductionChampionGeneration`, independently re-derive forecast promotion authority, replay reviewed non-model admissions, and exact-match all four champion identities against that planning bundle. Missing, future, forged or mismatched champion authority fails closed.
5. For every satisfying mandatory empirical claim, replay its typed empirical qualification evidence at the explicit release time and reconcile proof ID, canonical release subject, stable subject identity, experiment identity and season. Direct forecast/policy/scenario empirical proofs must bind the exact subjects carried by the replayed planning bundle.
6. For `PO-REFERENCE-SOLVER-PARITY-001`, replay the exact planning solver certificate, exact champion authorization/registry and the planning-v2 algorithmic worker qualification; reconcile the exact bundle planning result, objective, root action, trajectory, horizon, cutoff and tie-break policy.
7. Derive the ReleaseCertificate from the machine-readable AssuranceCase. There is no second readiness gate that can override this result.
8. Verify retained production control-plane qualification evidence **and bind it to the actual adapters being used**. ArtifactStore and ReleaseRegistry expose stable backend identities; those identities must exactly match the qualification. Both backends must be durable, shared, immutable/history-preserving and CAS-capable. `FileSystemArtifactStore` and `FileSystemReleaseRegistry` carry explicit `apex.reference.*` backend identities and remain structurally non-production even if a caller supplies green capability booleans.
9. Validate an explicit timezone-aware `created_at` and non-null `valid_until` with `valid_until > created_at`.
10. Seal a schema-v2 `ProductionPublicationAuthorization` containing the exact scope, bundle/world/runtime/manifest identities, exact champion-generation artifact, exact `created_at`/`valid_until`, AssuranceCase snapshot, proof-registry snapshot, ReleaseCertificate result and the content identity of the backend-qualification snapshot.
11. Construct exactly one immutable `ReleaseRecord` bound to that authorization artifact and the identical validity window. Its `ready_to_act` and `safe_to_act` fields are derived from authorization; they are never caller inputs.
12. If authorization is WITHHELD, retain immutable attempt evidence and require the production current pointer to remain unchanged.
13. If authorization is eligible, append and replay the exact immutable PUBLISHED ReleaseRecord, then compare-and-swap the current pointer from the observed predecessor to that exact release ID. A stale writer fails closed.
14. The answer surface resolves only the current PUBLISHED V2 ReleaseRecord and independently replays its publication authorization, schema-v2 planning bundle, planning-solver parity chain, manifest, AssuranceCase proof surface, empirical qualifications and authorization-bound backend qualification. The backend identities in that qualification must match the actual store/registry serving the answer. The caller supplies an explicit timezone-aware `as_of`; hidden wall-clock time is forbidden. Authority is withheld before `created_at` and at or after `valid_until`.
15. Immediately before returning authority, re-read the current pointer. Concurrent pointer drift withholds the answer rather than exposing the superseded release.
16. Persist the `ProductionCutoverReport` and CAS lineage as post-attempt immutable audit evidence.

A PUBLISHED-looking ReleaseRecord is not sufficient authority. V1 records, shadow records, CERTIFIED-only records, forged `ready=true` records, tactical schema-v1 bundles, incomplete/limited planning results, proof-class laundering, arbitrary empirical artifacts, wrong release subjects, unrelated/random solver artifacts, unqualified/non-champion solver workers, reference-filesystem publication attempts, cross-backend authorization replay, missing or mismatched backend identities, missing/expired validity windows, corrupt authorization, corrupt bundles/manifests, pointer drift and stale publication attempts are non-actionable.

## Status versus actionability

`WITHHELD` is a successful fail-closed outcome when evidence is incomplete. It never moves the production pointer and derives both readiness flags as false.

`PUBLISHED` is possible only after a blocker-free ReleaseCertificate, exact schema-v2 planning lineage, replay-valid point-in-time champion authority, replay-valid qualified planning-reference parity, complete typed proof lineage, identity-bound qualified production backend evidence, a valid explicit publication horizon and successful exact CAS. Only then do `ready_to_act` and `safe_to_act` derive true, and only until the retained `valid_until` horizon.

A green production-control-plane code/test implementation is therefore not itself a production cutover. Runtime publication remains correctly WITHHELD until the real production evidence is qualified.

## Current 2026/27 cutover blockers

The repository deliberately does not fabricate default production authorities. The registered V2 forecast-model, DecisionPolicy, scenario/dependence, reference-solver and learning-policy champion slots remain empty, and `config/experiments_v2.yaml` intentionally contains no retrospective production experiments. Existing retained calibration material does not authorize those promotions. In addition, the filesystem ArtifactStore and ReleaseRegistry are reference/local adapters; retained qualification evidence for a real durable shared production control plane is required before live cutover.

The receding-horizon planner and planning-v2 reference-solver mechanisms use synthetic worlds/workers in tests only. Passing those tests proves the mechanism and failure modes, not that a real 2026/27 policy/model/worker is qualified. No synthetic registry champion, qualification corpus or backend double may be copied into production configuration.

Those conditions are expected to keep a real production AssuranceCase/cutover WITHHELD until genuine no-hindsight qualification work supplies evidence.

## Immutable history and rollback

Publication never mutates an existing ReleaseRecord. Historical releases and their source artifacts remain addressable by content identity. A later release becomes current through another CAS transition. Rollback means a governed current-pointer transition to an already retained release only if that release is still valid under the applicable policy and proof surface; it does not rewrite historical bytes or resurrect an expired authorization.

## Relationship to Slice 12 and Slice 14

Slice 12 proves that the real release contract can be rehearsed while structurally non-actionable and while the production current pointer remains read-only. A shadow PASS is not cutover permission.

Slice 14 may begin only after a genuine production cutover is certified. Slice 14 then removes or disables competing V1 production writers and obsolete parallel readiness/publication paths while preserving historical replay evidence. Until that successful cutover exists, legacy production authority must not be removed prematurely.

## Machine-enforced surfaces

- `src/apex_fpl/core/champion_authority.py`
- `src/apex_fpl/core/production.py`
- `src/apex_fpl/core/production_proof_contract.py`
- `src/apex_fpl/core/experiments.py`
- `src/apex_fpl/core/production_bundle.py`
- `src/apex_fpl/core/planning.py`
- `src/apex_fpl/core/reference_solver_planning_io.py`
- `src/apex_fpl/core/reference_solver_planning_assurance.py`
- `src/apex_fpl/core/reference_solver_planning_qualification.py`
- `src/apex_fpl/control/artifact_store.py`
- `src/apex_fpl/control/experiment_registry.py`
- `src/apex_fpl/control/empirical_qualification_admission.py`
- `src/apex_fpl/control/champion_authority.py`
- `src/apex_fpl/control/learning_promotion_replay.py`
- `src/apex_fpl/control/production_backend_qualification.py`
- `src/apex_fpl/control/production_cutover.py`
- `src/apex_fpl/control/production_planning_bundle.py`
- `src/apex_fpl/control/production_reference_solver_binding.py`
- `src/apex_fpl/control/reference_solver_planning_qualification.py`
- `src/apex_fpl/core/production_authority.py`
- `src/apex_fpl/control/production_authority.py`
- `src/apex_fpl/control/release_registry.py`
- `src/apex_fpl/assurance/reference_solver_planning_exchange.py`
- `src/apex_fpl/assurance/planning_solver_parity.py`
- `src/apex_fpl/assurance/worker_authorization.py`
- `src/apex_fpl/workers/reference_solver_planning.py`
- `config/experiments_v2.yaml`
- `config/reference_solvers_v2.yaml`
- `config/proof_obligations.yaml` — empirical REQUIRED proofs, planning solver parity and `PO-PRODUCTION-CUTOVER-001`
- `config/requirements.yaml` — empirical qualification, decision assurance and production cutover traceability
- `docs/APEX_CHAMPION_AUTHORITY_V2.md`
- `docs/APEX_INVARIANTS.md`
- `docs/APEX_EMPIRICAL_QUALIFICATION_V2.md`
- `docs/APEX_RECEDING_HORIZON_PLANNER_V2.md`
- `tests/test_v2_empirical_qualification_plane.py`
- `tests/test_v2_empirical_qualification_edges.py`
- `tests/test_v2_empirical_qualification_traceability.py`
- `tests/test_v2_reference_solver_planning.py`
- `tests/test_v2_reference_solver_planning_qualification.py`
- `tests/test_v2_production_planning_bundle.py`
- `tests/test_v2_champion_authority.py`
- `tests/test_v2_production_cutover.py`
- `tests/test_v2_production_authority.py`
- `tests/test_v2_production_architecture.py`
- `tests/test_v2_production_traceability.py`
