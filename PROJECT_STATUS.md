# FPL Apex — production status

**Status date:** 4 September 2026

> Canonical human continuity/history is [`docs/FPL_APEX_MASTER_STATE.md`](docs/FPL_APEX_MASTER_STATE.md). Machine serving authority is [`docs/APEX_V2_AUTHORITY.json`](docs/APEX_V2_AUTHORITY.json) and outranks prose.

## Current verdict

# **APEX OPERATIONAL**

Apex V2 is the production FPL system for season **2026/27** and entry **63984**. Canonical production run #9 (`33850307770`; immutable run `33850307770-1`) completed successfully for GW3 and published a matching immutable public/private run pair under the authority-declared serving core.

The previously outstanding owner-private query gate is now closed. A dedicated private self-hosted macOS ARM64 runner (`fpl-apex-private-mac`) executes private query/continuity workflows with no `ubuntu-latest` fallback and no GitHub-hosted runner spend.

Private acceptance evidence:

- post-PR-#4 private strategy `latest` run `33867975181`: success;
- explicit exact run `33850307770-1`: strategy run `33868412431`, success;
- final restored authority-selected `latest`: strategy run `33868662109`, success;
- exact and final-latest narrow JSON outputs were byte-for-byte identical at SHA-256 `e50c4ebde19a2c68bfa4c38f33a6dd81f1d0922851f1e932bae522a898609d60`;
- both resolved immutable run `33850307770-1`, entry `63984`, exact 15-player TeamState, £0.5m bank, 1 free transfer and complete purchase/selling-price transfer state;
- final private post-merge master-state contract `33868662187`: success.

The historical GitHub-hosted billing failures remain provenance only and are not current blockers.

## Production authority

Immutable forensic base (`frozen_engine_sha`): `99cc7b51b0cff45462b567084cb1844cfe0a456f`

Current serving core: read `production_core_sha` from `APEX_V2_AUTHORITY.json`. At this closure snapshot it is `c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437`.

- Frozen engine PR: **#90**, draft/open/unmerged, policy `NEVER_MERGE_OR_ADVANCE`.
- Operations/research control plane: `main`; verify the current head live rather than treating a prose SHA as permanent.
- Canonical production workflow: `.github/workflows/apex-v2-daily-production.yml`.
- Sole serving forecast provider: **AIrsenal**, H1–H8.
- Apex Proprietary, Dastan, PITCHSIDE and OpenFPL are shadow/diagnostic only and have no serving authority.
- Research/tournament output has `production_influence = NONE`; no blending, voting or automatic challenger promotion.
- Official FPL remains factual authority for identity, club, position, price, status/availability, fixtures and deadlines.

PR #122 separated immutable-base authority from the serving-core pointer. PR #146 permanently repaired duplicate production optimisation/incorrect one-candidate semantics and made publication witness-only. PR #147 promoted the repaired serving core through `production_core_sha`. PR #149 restored normal Deadline Watch after the controlled one-shot production dispatch.

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

Release ID `382559137`, immutable, published `2026-09-04T07:51:49Z`.

Matching owner-private manager/evaluation/presentation releases share run identity `33850307770-1`; private payload details stay in the private repository and its companion master ledger.

## Owner-private query capability

The private repository is the approved owner-state/query plane. `latest` is authority-first, not publication-time-first: it resolves current public production authority, filters private manager releases by the exact linked `public_attempt_id`, verifies GitHub asset digests and Apex attestations, and fails closed if no authority-correct private release exists.

A fresh connected agent can therefore recover exact current persisted owner state without reconstructing the squad from chat memory. Private query output remains narrow and does not expose `private-auth`, credentials, commitment keys or unfiltered private provider payloads.

Operational does not mean a historical immutable recommendation remains fresh indefinitely. Production deadline/freshness/auth/source gates still govern whether a new manager-facing recommendation is actionable.

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
6. use the private query boundary for owner-specific state;
7. update the canonical master ledger in the same change as every tracked repository change.

`AGENTS.md`, `CLAUDE.md`, `scripts/check_master_state_sync.py` and required Apex CI encode/enforce this continuity contract.
