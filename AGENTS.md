# FPL Apex Agent Contract

This repository is a production FPL decision system. Do not treat a new chat/session as a blank-slate design exercise.

## Mandatory preflight

Before any substantive analysis or repository change, read in this order:

1. `docs/FPL_APEX_MASTER_STATE.md` — canonical human/project continuity ledger.
2. `docs/APEX_V2_AUTHORITY.json` — machine production authority; it outranks prose.
3. `docs/CURRENT_STATE.md` and `docs/APEX_OPERATING_MANUAL.md`.
4. The specific runbook/contract/tests for the surface you will touch.
5. Verify live GitHub state and relevant immutable releases/workflows before relying on mutable facts.

For owner-specific squad/transfer questions, use the approved private `mcnuggets651/fpl` query boundary. Never reconstruct manager state from conversation memory, screenshots, historical recommendation files, or an old squad.

## Non-negotiable invariants

- PR #90 / `frozen_engine_sha` is forensic lineage: `NEVER_MERGE_OR_ADVANCE`.
- Production serving code is selected independently by `production_core_sha` in `docs/APEX_V2_AUTHORITY.json`.
- AIrsenal is the current sole serving provider H1–H8 unless machine governance is explicitly changed through the existing promotion mechanism.
- Research/shadow providers have no implicit production influence; no blending, voting, silent fallback or automatic promotion.
- Official FPL is factual authority for identity, club, FPL position, price, availability/status, fixtures/deadlines and authenticated manager mechanics.
- Production uses one frozen snapshot, no network during solve, exact mechanics, max-EV legal optimisation and immutable public/private publication.
- Publication must not rerun the optimiser; it performs deterministic frozen-witness verification.
- Private manager state, credentials and unfiltered private payloads must never be copied into this public repository.
- Do not reopen closed architecture/model work without new reproducible evidence of a production defect.

## Mandatory same-change documentation

Every tracked repository change must update `docs/FPL_APEX_MASTER_STATE.md` in the same PR/commit, unless the master state is the only tracked file changed.

The update must record what changed, why, proof/tests, affected invariants/authority, what did not change and any remaining next action. CI enforces this rule with `scripts/check_master_state_sync.py`.

Do not create a second competing master-state file. Update the canonical ledger and any subordinate docs that need synchronization.

## Before claiming completion

- run/observe the relevant tests and required GitHub checks;
- reconcile the result with `APEX_V2_AUTHORITY.json`;
- update the master ledger with exact evidence;
- do not call external account/billing failures Apex code failures;
- do not claim `APEX OPERATIONAL` unless the master ledger's explicit acceptance gates are actually satisfied.
