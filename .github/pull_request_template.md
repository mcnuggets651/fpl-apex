## Summary

<!-- What changed and why? -->

## Capability declaration

<!-- These lines are machine-read by scripts/check_capability_registry.py. Use comma-separated registry IDs and yes/no exactly where requested. -->

Apex-Capabilities: 
Apex-Authority-Changed: no
Apex-Invariants-Changed: none
Apex-Decisions-Reopened: none

## Authority / production impact

- [ ] I read `docs/FPL_APEX_MASTER_STATE.md` and `docs/APEX_V2_AUTHORITY.json` before making substantive changes.
- [ ] I read `docs/APEX_CAPABILITY_REGISTRY.yaml`, `docs/APEX_ARCHITECTURE.md` and the runbooks/tests for every declared capability.
- [ ] I verified relevant live GitHub/release state.
- [ ] This PR does **not** merge/advance frozen PR #90 or silently change serving authority.
- [ ] Any owner-private state remains in `mcnuggets651/fpl`, not this public repository.

## Mandatory continuity update

- [ ] `docs/FPL_APEX_MASTER_STATE.md` is updated in this PR (unless it is the only changed tracked file).
- [ ] The master update records what changed, why, evidence/tests, affected invariants/authority, what did not change and the next action/blocker.

## Verification

<!-- List exact local tests, CI runs, immutable release evidence, mutation/adversarial checks or explain why a check is not applicable. -->

## Closed-decision check

- [ ] I am not reopening a previously closed model/architecture decision without new reproducible evidence documented in the master state and `Apex-Decisions-Reopened` metadata.
- [ ] If a decision's status/supersession changed, `docs/APEX_DECISION_INDEX.yaml` is updated without rewriting historical rationale in `docs/APEX_DECISIONS.md`.
