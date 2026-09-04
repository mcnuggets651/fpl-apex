# FPL Apex — production status

**Status date:** 4 September 2026

> Canonical human continuity/history is [`docs/FPL_APEX_MASTER_STATE.md`](docs/FPL_APEX_MASTER_STATE.md). Machine serving authority is [`docs/APEX_V2_AUTHORITY.json`](docs/APEX_V2_AUTHORITY.json) and outranks prose.

## Current verdict

**PRODUCTION PIPELINE PASSED; PRIVATE QUERY ACCEPTANCE BLOCKED BY GITHUB BILLING**

Apex V2 is the production FPL system for season **2026/27** and entry **63984**. Canonical production run #9 (`33850307770`; immutable run `33850307770-1`) completed successfully for GW3 and published a matching immutable public/private run pair using serving core `c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437`.

The only remaining acceptance gate is owner-private strategy query execution in explicit-run and authority-selected `latest` modes. GitHub rejected both jobs before runner allocation because of account billing/spending state. A 4 September retry of `latest` again had zero steps and `runner_id=0`; this is not evidence of query code failure.

Do not reopen model/architecture development because of this external gate. The exact closure procedure is in the master ledger.

## Production authority

- Immutable forensic base (`frozen_engine_sha`): `99cc7b51b0cff45462b567084cb1844cfe0a456f`.
- Current serving core: read `production_core_sha` live from machine authority; at this snapshot it is `c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437`.
- Frozen engine PR: **#90**, draft/open/unmerged, policy `NEVER_MERGE_OR_ADVANCE`.
- Operations/research control plane: `main`; verify the current head live rather than treating a prose SHA as permanent.
- Canonical production workflow: `.github/workflows/apex-v2-daily-production.yml`.
- Sole serving forecast provider: **AIrsenal**, H1–H8.
- Apex Proprietary, Dastan, PITCHSIDE and OpenFPL are shadow/diagnostic only and have no serving authority.
- Research/tournament output has `production_influence = NONE`; no blending, voting or automatic challenger promotion.
- Official FPL remains factual authority for identity, club, position, price, status/availability, fixtures and deadlines.

PR #122 separated immutable-base authority from the serving-core pointer. PR #146 permanently repaired duplicate production optimisation/incorrect one-candidate semantics and made publication witness-only. PR #147 promoted the exact repaired serving core through `production_core_sha`. PR #149 restored normal Deadline Watch after the controlled one-shot production dispatch.

## Successful production proof

Run #9 passed:

- authenticated owner-state recovery;
- Official FPL acquisition/re-anchor;
- AIrsenal H1–H8 generation;
- single frozen solve;
- exact mechanics/certification;
- deterministic publication witness;
- private prerequisite publication;
- immutable public final publication.

Public final:

`apex-v2/final/2026-2027/33850307770-1`

Release ID `382559137`, immutable, published `2026-09-04T07:51:49Z`, target core `c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437`.

Matching owner-private manager/evaluation/presentation releases share run identity `33850307770-1`; private payload details stay in the private repository and its companion master ledger.

## Current operations

The serving recommendation is the immutable Apex V2 final produced by the exact authority-declared production core. Repository V1/V1.5 generated recommendation files and `scripts/run_apex.py` remain historical/test surfaces, not live authority.

Supporting workflows are separated by role:

- auth keepalive — authentication state only;
- deadline watch — dispatches the canonical production workflow near a real deadline;
- daily evaluation — prospective scoring of previously sealed surfaces;
- prospective tournament — non-serving provider evaluation;
- Decision Quality — non-serving prospective counterfactual decision-edge research.

The historical `archive/workflows/` tree is forensic evidence and must not be modified/resurrected as live publishing code.

## Governance and continuity

Before substantive work:

1. read `docs/FPL_APEX_MASTER_STATE.md`;
2. read `docs/APEX_V2_AUTHORITY.json`;
3. read `docs/CURRENT_STATE.md` and `docs/APEX_OPERATING_MANUAL.md`;
4. verify live `main`, PR #90, ruleset/checks, relevant workflow runs and immutable releases;
5. never reconstruct the manager squad from conversation memory;
6. update the canonical master ledger in the same change as every tracked repository change.

`AGENTS.md`, `CLAUDE.md`, `scripts/check_master_state_sync.py` and required Apex CI encode/enforce this continuity contract.
