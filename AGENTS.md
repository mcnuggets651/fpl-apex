# FPL Apex Agent Contract

This repository is a production FPL decision system. Do not treat a new chat/session as a blank-slate design exercise.

## Mandatory preflight

Before any substantive analysis or repository change, read in this order:

1. `docs/FPL_APEX_MASTER_STATE.md` — canonical human/project continuity ledger.
2. `docs/APEX_V2_AUTHORITY.json` — machine production authority; it outranks prose.
3. `docs/CURRENT_STATE.md` and `docs/APEX_OPERATING_MANUAL.md`.
4. `docs/APEX_CAPABILITY_REGISTRY.yaml` — canonical semantic capability/change-surface index.
5. `docs/APEX_ARCHITECTURE.md` — single current cross-repository V2 system map.
6. The specific runbook/contract/tests referenced by the registry for the capability being touched.
7. Verify live GitHub state and relevant immutable releases/workflows before relying on mutable facts.

For owner-specific squad/transfer questions, use the approved private `mcnuggets651/fpl` query boundary. Never reconstruct manager state from conversation memory, screenshots, historical recommendation files, or an old squad.

## Non-negotiable invariants

- PR #90 / `frozen_engine_sha` is forensic lineage: `NEVER_MERGE_OR_ADVANCE`.
- Production serving code is selected independently by `production_core_sha` in `docs/APEX_V2_AUTHORITY.json`.
- Current provider roles/horizons come only from machine authority; do not copy them into a second authority source.
- Research/shadow providers have no implicit production influence; no blending, voting, silent fallback or automatic promotion.
- Official FPL is factual authority for identity, club, FPL position, price, availability/status, fixtures/deadlines and authenticated manager mechanics.
- Production uses one frozen snapshot, no network during solve, exact mechanics, max-EV legal optimisation and immutable public/private publication.
- Publication must not rerun the optimiser; it performs deterministic frozen-witness verification.
- Private manager state, credentials and unfiltered private payloads must never be copied into this public repository.
- Do not reopen closed architecture/model work without new reproducible evidence of a production defect.

## Capability/change-surface contract

Before changing the repository:

1. identify the affected capability IDs in `docs/APEX_CAPABILITY_REGISTRY.yaml`;
2. read their authority references, runbooks, invariants, failure behavior and tests;
3. declare those IDs in the PR metadata line `Apex-Capabilities:`;
4. state whether machine authority changes, which invariants change and whether any closed decisions are reopened;
5. keep the diff inside registered `change_surface` paths or update the registry explicitly with tests.

`scripts/check_capability_registry.py` enforces workflow/script registration, symbolic/ref-aware entry points, research/serving boundaries, decision-index completeness and changed-path ↔ declared-capability consistency. The registry is a semantic index only; it must not copy current production SHAs, run IDs, owner squad/bank/FT/prices, latest release identity or live provider health.

## Mandatory same-change documentation

Every tracked repository change must update `docs/FPL_APEX_MASTER_STATE.md` in the same PR/commit, unless the master state is the only tracked file changed.

The update must record what changed, why, proof/tests, affected invariants/authority, what did not change and any remaining next action. CI enforces this rule with `scripts/check_master_state_sync.py`.

Do not create a second competing master-state file, capability registry, current architecture map or runbook index. Update the canonical surfaces and subordinate docs that need synchronization.

## Decision history

`docs/APEX_DECISIONS.md` is append-only rationale/history. `docs/APEX_DECISION_INDEX.yaml` is the machine-readable status/supersession index. Do not silently rewrite old decisions to make them look current; classify them as active/partially superseded/superseded/historical and point to the decision that changed authority.

## Before claiming completion

- run/observe the relevant tests and required GitHub checks;
- reconcile the result with `APEX_V2_AUTHORITY.json`;
- update the master ledger with exact evidence;
- verify capability-registry enforcement is green for the exact PR head;
- do not call external account/billing failures Apex code failures;
- do not claim `APEX OPERATIONAL` unless the master ledger's explicit acceptance gates are actually satisfied.
