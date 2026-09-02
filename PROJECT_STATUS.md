# FPL Apex — production status

**Status date:** 2 September 2026

Apex V2 is the production FPL system for season **2026/27** and entry **63984**. The machine-readable authority is [`docs/APEX_V2_AUTHORITY.json`](docs/APEX_V2_AUTHORITY.json); canonical documentation and governance checks must agree with it.

## Production authority

- Frozen certified engine: `99cc7b51b0cff45462b567084cb1844cfe0a456f`.
- Frozen engine PR: **#90**, draft/open/unmerged. It is not an operations branch and must not be merged or advanced.
- Operations/research control plane: `main`. The live `main` head is intentionally not frozen in this document; verify it directly on GitHub at session start.
- V2 authority reconciliation was merged in PR #115 and its post-merge documentation closure in PR #116.
- Canonical production workflow: `.github/workflows/apex-v2-daily-production.yml`.
- Sole serving forecast provider: **AIrsenal**, H1–H8.
- Apex Proprietary, Dastan, PITCHSIDE and OpenFPL are shadow/diagnostic only and have no serving authority.
- Research/tournament output has `production_influence = NONE`; there is no blending, voting or automatic challenger promotion.
- Official FPL remains factual authority for identity, club, position, price, status/availability and fixtures.

The serving recommendation is the immutable Apex V2 final release produced by the frozen engine. Repository V1/V1.5 generated recommendation files and `scripts/run_apex.py` remain historical/test surfaces; they are not the live production authority.

## Current operations

Apex V2 Daily Production checks out the frozen SHA, authenticates the exact configured manager, captures Official FPL authority before provider work, acquires/freeze-checks provider surfaces, re-anchors Official FPL, solves with network access disabled and publishes private prerequisites before the immutable public final.

Supporting workflows are separated by role:

- auth keepalive — authentication state only;
- deadline watch — dispatches the canonical production workflow near a real deadline;
- daily evaluation — prospective scoring of previously sealed surfaces;
- prospective tournament — non-serving provider evaluation;
- Decision Quality — non-serving prospective counterfactual decision-edge research.

All executable GitHub workflows use exact commit pins for the certified Node-24-native GitHub Actions generations. Future GitHub Action updates are proposed by Dependabot through the normal protected pull-request path. The historical `archive/workflows/` tree is forensic evidence and the V2 Ops Contract rejects modifications to it.

See [`docs/APEX_V2_DAILY_OPERATIONS.md`](docs/APEX_V2_DAILY_OPERATIONS.md), [`docs/APEX_V2_PROSPECTIVE_TOURNAMENT.md`](docs/APEX_V2_PROSPECTIVE_TOURNAMENT.md), and [`docs/operations/PARALLEL_DECISION_LAB.md`](docs/operations/PARALLEL_DECISION_LAB.md).

## GW3 decision-quality acceptance — COMPLETE

Canonical prospective candidate:

`apex-v2/tournament-candidate/2026-2027/33590896695-1`

Official GW3 deadline:

`2026-09-04T17:30:00Z`

PR #114 repaired the exact-task runtime contract without changing frozen decision semantics. The frozen transfer optimiser can legally consume 34 minutes of MILP allowance; Decision Quality grants 50 minutes per independent matrix solve and CI derives/guards that bound against the frozen source.

Corrected Decision Quality run #10 is run `33643925982`, bound to control-plane SHA `e123fb312015a620795f343f503f8c214699afb4`. It completed successfully on 2 September 2026. All **8/8** required fresh tasks sealed successfully before the GW3 deadline, including the exact production baseline and the previously timing-out Apex Proprietary availability overlay. Every solve retained the frozen-worktree proof.

Canonical assembly also completed successfully and published the immutable private lab:

`apex-v2/private-decision-lab/2026-2027/33590896695-1`

The assembler requires every deterministic staging task, validates each task fingerprint and attestation, rejects any constituent not sealed/published predeadline, requires exact production-baseline reproduction, forbids postdeadline decision backfill, and keeps the lab non-serving. The assembled lab contains eight decision variants and has `production_influence = NONE`, `serving_authorized = false`, and no automatic serving change. `postoutcome` also completed successfully; because GW3 outcomes did not yet exist, it correctly made no learning or serving change.

This is the live acceptance proof for the Decision Quality runtime repair. No further GW3 acceptance work is pending.

## Governance status

**GREEN.** The Project Brain, ChatGPT/operator instructions, machine authority, generic governance checker, repository workflow-contract tests and active workflow inventory describe the same frozen V2 constitution.

Legacy executable publishers (`pinnacle.yml`, `airsenal.yml`, `refresh-core-pin.yml`, `gw1-final-2026.yml`) are preserved under `archive/workflows/` and are absent from GitHub's executable workflow directory. The generic governance checker recognizes exactly one serving production workflow, while the V2 Ops Contract fails if legacy publishers return, canonical authority documents revive obsolete V1/Pinnacle production claims, an operations PR crosses into frozen `src/`/`config/`, or the forensic workflow archive is modified.

Main protection ruleset `21759706` is the required live control: pull-request enforcement, strict required `test` / `contract` / `readiness` checks, and no bypass actors. Verify it live rather than trusting this prose if repository state is being changed.

## Startup rule

For a new operator or ChatGPT session:

1. read `docs/APEX_V2_AUTHORITY.json`;
2. read `docs/CURRENT_STATE.md`;
3. read `docs/APEX_MASTER_CONTEXT.md` and `docs/APEX_OPERATING_MANUAL.md`;
4. verify live `main`, PR #90, ruleset `21759706` and the relevant immutable Apex V2 release/workflow state;
5. never reconstruct the manager squad from conversation memory.
