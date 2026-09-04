# FPL Apex — Current State

**Last updated:** 4 September 2026

> **Read first:** [`FPL_APEX_MASTER_STATE.md`](FPL_APEX_MASTER_STATE.md) is the canonical human/project continuity ledger. Machine authority remains [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json), which outranks prose. This file is a shorter operational view and must not be used as a competing master state.

## Current closure status

**PRODUCTION PIPELINE PASSED; PRIVATE QUERY ACCEPTANCE BLOCKED BY GITHUB BILLING**

Canonical production run #9 (`33850307770`, immutable run `33850307770-1`) completed successfully for GW3 under the then-current authority-declared serving core. Authentication, Official FPL acquisition, AIrsenal H1–H8 generation, frozen solve, deterministic publication witness and matched immutable public/private publication all passed. Exact historical core identity is preserved in immutable release evidence and the canonical master ledger, not copied here as a movable current pointer.

The only remaining acceptance gate is execution of the private strategy-query bridge in exact and `latest` modes. GitHub rejected both jobs before runner allocation because of account billing/spending state; a second retry of `latest` on 4 September again produced zero job steps and `runner_id=0`. This is not bridge-code failure. Do not reopen model development because of it.

Canonical machine authority: [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json).

Immutable forensic base (`frozen_engine_sha`): `99cc7b51b0cff45462b567084cb1844cfe0a456f`

Current serving core: read `production_core_sha` from `APEX_V2_AUTHORITY.json`.

## Production now

PR #90 and the immutable forensic/base SHA remain permanently anchored at `99cc7b51b0cff45462b567084cb1844cfe0a456f`. PR #90 stays open, draft and unmerged; operations and successor promotion must never merge or advance it.

The authority-declared serving core is independently pinned by `production_core_sha`. PR #122 separated immutable forensic lineage from the serving pointer. Successor promotions, including the PR #147 promotion of the PR #146 single-solve/publication-witness repair, move only `production_core_sha` through explicit certification.

The default branch `main` is the live operations/research control plane. Do not copy a historical `main` SHA into future reasoning as if it were permanent: verify the current signed head directly on GitHub.

The only serving production workflow is:

`.github/workflows/apex-v2-daily-production.yml`

**AIrsenal** is the sole serving provider for H1–H8. Apex Proprietary is shadow H1–H8; Dastan is shadow H1 only; PITCHSIDE and OpenFPL are external diagnostic/shadow providers. All challenger/research surfaces are non-serving and may not be blended, voted into production or promoted automatically.

Official FPL remains factual authority for identity, club, FPL position, price, status/availability and fixtures.

## Serving contract

An actionable recommendation comes only from the authenticated Apex V2 production chain running the exact authority-declared `production_core_sha` and its immutable final release. Production must have exact manager state for entry 63984, one frozen input snapshot, a qualified AIrsenal H1–H8 surface, legal exact optimisation/mechanics and successful immutable publication.

Daily Production proves that `production_core_sha` descends from `frozen_engine_sha`, materializes the exact serving core in a detached worktree, and binds attempt intent, frozen acquisition snapshot and final publication to the same core SHA.

If authentication, factual authority, provider qualification, snapshot identity, serving-core provenance or immutable publication is unsafe, production fails closed. Research output cannot substitute for a missing serving release.

Legacy `scripts/run_apex.py`, Pinnacle/Elite flows and repository-generated recommendation files are historical/test compatibility surfaces, not current production authority.

## GW3 prospective research — ACCEPTED

Canonical tournament candidate:

`apex-v2/tournament-candidate/2026-2027/33590896695-1`

Official GW3 deadline:

`2026-09-04T17:30:00Z`

PR #112 added the prospective decision-edge lab. PR #113 made it parallel/resumable using immutable per-task staging. PR #114 corrected the individual heavy-task runtime contract from 30 to 50 minutes without changing serving decision semantics. A regression derives the 34-minute theoretical MILP allowance from the immutable evaluator source and requires explicit orchestration headroom.

Corrected Decision Quality run #10 (`33643925982`) ran under control-plane SHA `e123fb312015a620795f343f503f8c214699afb4` and completed successfully on 2 September 2026. All eight deterministic fresh tasks sealed before the deadline. The exact production baseline reproduced successfully; the formerly timing-out Apex Proprietary availability experiment also completed; every task preserved its immutable-worktree proof.

Canonical assembly succeeded and published the immutable private lab:

`apex-v2/private-decision-lab/2026-2027/33590896695-1`

The canonical lab contains eight variants and remains explicitly non-serving: `production_influence = NONE`, `serving_authorized = false`, no promotion authority and no automatic serving change. The assembler validates immutable task fingerprints/attestations, requires every constituent decision to have been sealed predeadline and forbids postdeadline decision backfill. Dastan remains H1-only and no invented Dastan H2+ pure-provider plan exists.

The `postoutcome` stage completed successfully. With GW3 outcomes not yet available it correctly published no realized decision-quality result and made no learning or serving change. GW3 runtime/decision-lab acceptance is therefore complete; later outcome scoring is normal prospective operation, not an unfinished acceptance gate.

## Operations health

Structurally healthy:

- Apex V2 Daily Production;
- authenticated owner-state recovery/rotation;
- deadline watcher;
- daily prospective evaluation;
- prospective tournament;
- immutable private release store boundaries;
- Decision Quality parallel/resumable exact-task runtime;
- Node-24-native GitHub Actions execution surface;
- independently governed immutable-base and serving-core authority;
- lock-aware production/readiness installation;
- single-solve production and deterministic publication witness.

Executable workflows use exact commit pins for the certified Node-24-native generations of `actions/checkout`, `actions/setup-python`, `actions/cache` and `actions/upload-artifact`. A dedicated operations regression rejects stale/mutable action references, and Dependabot proposes future GitHub Actions updates weekly through the normal protected pull-request path.

The historical `archive/workflows/` directory is forensic evidence. The V2 Ops Contract rejects any change to that archive while separately rejecting any resurrection of retired publishers into `.github/workflows`.

The OpenFPL current-history observer deliberately resolves its moving upstream history ref to a full immutable commit before reading rows and records that resolved SHA. This is an audited non-serving exception to static pinning: freezing the observer to an old history baseline would prevent new completed Gameweeks from becoming observable.

## Source of truth for continuation

For substantive work:

1. read `FPL_APEX_MASTER_STATE.md` completely;
2. read `APEX_V2_AUTHORITY.json`;
3. read this file and `APEX_OPERATING_MANUAL.md`;
4. read the relevant V2 implementation/research runbook;
5. verify live `main`, PR #90, `production_core_sha`, main ruleset and relevant workflow/release state before changing anything;
6. update `FPL_APEX_MASTER_STATE.md` in the same change as every tracked repository change, as enforced by CI.

Do not use an old GW1 squad or historical generated recommendation as current manager state. Do not invent a squad from memory. Owner-specific state is recovered through the private repository/query boundary.
