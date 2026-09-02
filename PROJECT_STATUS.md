# FPL Apex — production status

**Status date:** 2 September 2026

Apex V2 is the production FPL system for season **2026/27** and entry **63984**. The machine-readable authority is [`docs/APEX_V2_AUTHORITY.json`](docs/APEX_V2_AUTHORITY.json); canonical documentation and governance checks must agree with it.

## Production authority

- Frozen certified engine: `99cc7b51b0cff45462b567084cb1844cfe0a456f`.
- Frozen engine PR: **#90**, draft/open/unmerged. It is not an operations branch and must not be merged or advanced.
- Operations/research control plane: `main`.
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

See [`docs/APEX_V2_DAILY_OPERATIONS.md`](docs/APEX_V2_DAILY_OPERATIONS.md), [`docs/APEX_V2_PROSPECTIVE_TOURNAMENT.md`](docs/APEX_V2_PROSPECTIVE_TOURNAMENT.md), and [`docs/operations/PARALLEL_DECISION_LAB.md`](docs/operations/PARALLEL_DECISION_LAB.md).

## GW3 decision-quality acceptance

Canonical prospective candidate:

`apex-v2/tournament-candidate/2026-2027/33590896695-1`

Official GW3 deadline:

`2026-09-04T17:30:00Z`

PR #114 repaired the exact-task runtime contract without changing frozen decision semantics. The frozen transfer optimiser can legally consume 34 minutes of MILP allowance; Decision Quality now grants 50 minutes per independent matrix solve and CI derives/guards that bound against the frozen source.

GW3 runtime acceptance is complete only when all required predeadline task releases exist, canonical assembly succeeds, exact baseline reproduction is verified, every constituent decision is predeadline, the immutable canonical lab is validated and the overall workflow is green. Missing decisions may never be reconstructed after the deadline.

## Governance status

The Project Brain and generic governance layer are being reconciled to the V2 constitution. Legacy executable publishers (`pinnacle.yml`, `airsenal.yml`, `refresh-core-pin.yml`, `gw1-final-2026.yml`) are forensic history only and belong under `archive/workflows/`, outside GitHub's executable workflow directory.

The generic governance checker must treat exactly one workflow as serving production and must fail if canonical authority documents revive obsolete V1/Pinnacle production claims.

## Startup rule

For a new operator or ChatGPT session:

1. read `docs/APEX_V2_AUTHORITY.json`;
2. read `docs/CURRENT_STATE.md`;
3. read `docs/APEX_MASTER_CONTEXT.md` and `docs/APEX_OPERATING_MANUAL.md`;
4. verify live `main`, PR #90 and the relevant immutable Apex V2 release/workflow state;
5. never reconstruct the manager squad from conversation memory.
