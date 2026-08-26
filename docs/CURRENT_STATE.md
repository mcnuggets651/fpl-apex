# Apex FPL — Current State

Operating authority: [`APEX_OPERATING_MANUAL.md`](APEX_OPERATING_MANUAL.md).

**Last updated:** 2026-08-26

## Production status

- Repository: `mcnuggets651/fpl-apex`.
- Production branch remains `main`.
- The V2 control-plane stack is being built in reviewed, unmerged PRs; an open V2 PR must never be described as production merely because its CI is green.
- **Actual V2 production cutover is WITHHELD.** There is no authority to expose a V2 recommendation until the exact current `PUBLISHED` release, publication authorization, production planning bundle and all mandatory proofs replay successfully on qualified durable shared backends within their validity window.
- No production forecast-model, DecisionPolicy, scenario or planning reference-solver champion is fabricated by configuration.
- `config/experiments_v2.yaml` contains no retrospective qualification shortcut. Empirical production qualification must be prospectively predeclared and no-hindsight.

## Current V2 implementation stack

### Certified pre-cutover foundation

The certified stack through PR #83 provides the immutable V2 control plane, typed empirical-qualification admission, exact DecisionPolicy support contracts and independent assurance foundations. It deliberately does not create production champions or perform cutover.

### PR #84 — exact receding-horizon planner

Branch: `v2/receding-horizon-planner`  
PR: #84 — **draft/open/unmerged**

PR #84 closes the structural gap between tactical current-Gameweek analysis and production-shaped max-EV-over-time decision execution:

- hypothetical planning state is typed separately from `CURRENT_EXACT` ManagerState truth;
- exact multi-Gameweek transitions cover realised selling finance, free-transfer banking, normal transfers, Wildcard, Free Hit and set-specific chip persistence/reversal;
- terminal chip-option reserve is part of the governed horizon objective;
- one exact immediately executable current `DecisionAction` is exposed from the selected trajectory;
- production planning requires a `FULL_OFFICIAL` CandidateUniverse and complete `OPTIMAL` zero-gap solve;
- planning states/results and their state/rules lineage replay offline under content identity;
- robustness EV-regret is anchored to the governed planning selection objective while realised scenario scoring remains fixed-current-action analysis;
- independent reference-solver parity is versioned as planning-v2 and independently reconstructs the horizon search rather than broadening tactical-v1 evidence;
- planning-worker qualification is replay-derived algorithmic evidence with explicit banking, transfer-finance, chip-surface, terminal-reserve, root-action, trajectory and zero-gap coverage;
- production solver parity requires the exact qualified champion authorization/certificate for the exact `PlanningResultId`, horizon, cutoff, objective, root action and selected trajectory;
- production publication authority is migrated to schema-v2 `ProductionPlanningBundle`; the legacy tactical/schema-v1 `ProductionDecisionBundle` is retained only as historical/mechanism evidence;
- constitutional proof obligations, requirements and invariants are planning-v2-bound and guarded by executable traceability tests.

The strong synthetic planning world used by solver qualification remains mechanism-only test evidence. It is not a real production champion or empirical football evidence.

### Certification state

The code/governance candidate immediately before this Project Brain refresh was `8d621541c3e19af91658642042b6da44a1644ca3`.

- V2 Shadow Production run `32924061255` succeeded on that exact pre-documentation head: 15/15 shadow contract tests and Ruff passed.
- Apex CI run `32924061244` was still executing full pytest when this documentation maintenance was prepared.
- This documentation refresh changes the branch SHA, so **final PR #84 certification must use a fresh same-head Apex CI + V2 Shadow Production pair after this commit**. Prior runs are supporting evidence only, not certification of the new head.

## Runtime-test architecture

The planning assurance tests now separate two responsibilities without weakening production replay:

- ordinary production CAS/expiry/authority tests use a real but minimal two-Gameweek `FULL_OFFICIAL` planning world so they do not repeatedly solve irrelevant transfer combinatorics;
- dedicated planner/reference-solver/qualification/parity tests retain the stronger 16-player banking, financed-transfer and positive terminal-reserve world;
- identical synthetic fixture bytes may be reused across isolated test ArtifactStores, but production qualification, authorization and replay code itself is not cached or bypassed;
- qualification verification intentionally re-derives the certificate and re-executes the independent worker.

## Remaining production blockers

### 1. Durable shared production backend — implementation blocker

The repository currently implements only:

- `FileSystemArtifactStore` — backend ID `apex.reference.filesystem-artifact-store.v1`;
- `FileSystemReleaseRegistry` — backend ID `apex.reference.filesystem-release-registry.v1`.

Both are explicitly reference/local adapters and are structurally disqualified from production. GitHub Actions artifacts are transitional/supplemental evidence, not the sole durable V2 authority store.

A subsequent slice must implement deployable durable shared ArtifactStore and ReleaseRegistry adapters with immutable content identity/history and atomic stale-writer-safe CAS, then qualify the **actual deployed backend identities** using retained operational evidence. Configuration booleans cannot substitute for that evidence.

### 2. Real production champions — qualification blocker

The control plane may define candidate artifacts and registries, but production admission still requires genuine registered champions within exact season/horizon/time scope. Synthetic test certificates never satisfy this.

### 3. Empirical football/model evidence — time/no-hindsight blocker

Forecast model, DecisionPolicy, realised scenario convergence, model evaluation and model promotion production proofs require predeclared typed experiments. Known historical outcomes cannot be relabelled retrospectively as V2 qualification. Where sufficient predeclared evidence does not exist, qualification must proceed prospectively as outcomes become available.

### 4. Production cutover — deliberately blocked

Cutover remains WITHHELD until every mandatory proof is replay-valid on the exact schema-v2 production planning bundle, exact runtime, exact qualified champions and exact qualified shared backend identities. Only a current unexpired `PUBLISHED` V2 release can become answer authority.

### 5. Slice 14 — blocked

Slice 14 remains blocked until a real V2 `PUBLISHED` production release exists. PR #66 remains archaeology/regression evidence only.

## Next implementation sequence

1. Finish PR #84 final same-head certification and keep it draft/open/unmerged until explicit merge approval.
2. Build and test the durable shared production ArtifactStore/ReleaseRegistry adapters without weakening the existing reference-adapter rejection or backend-identity binding.
3. Qualify only an actually deployed backend using retained operational evidence for durability, access control, recovery, integrity, concurrency/CAS and identity.
4. Register prospective no-hindsight experiments/candidates where empirical production qualification is still absent; never backfill already-known outcomes.
5. Create real champions only after their exact qualification contracts pass.
6. Assemble and replay a genuine schema-v2 `ProductionPlanningBundle` plus all mandatory assurance evidence.
7. Perform cutover only if the complete AssuranceCase authorizes an exact time-bounded PUBLISHED release on the qualified shared backend.
8. Begin Slice 14 only after that real production publication exists.

## User-facing FPL boundary

Until the V2 production authority chain above passes, do not invent or manually choose a squad and call it Apex V2. A user-facing Apex-labelled recommendation must come from the canonical authority contract; otherwise report the blocker explicitly.
