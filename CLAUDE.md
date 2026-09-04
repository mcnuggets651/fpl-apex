# Claude / AI Maintainer Instructions — FPL Apex

The mandatory repository contract is `AGENTS.md`.

Before doing substantive work, read completely:

1. `docs/FPL_APEX_MASTER_STATE.md`
2. `docs/APEX_V2_AUTHORITY.json`
3. `docs/CURRENT_STATE.md`
4. `docs/APEX_OPERATING_MANUAL.md`
5. the relevant implementation/runbook/tests

Then verify live GitHub/release/workflow facts before relying on mutable state.

Do not restart architecture design, merge/advance frozen PR #90, reconstruct owner state from memory, let research influence production implicitly, rerun optimisation in publication, weaken deterministic/integrity gates, or put private manager/auth material in the public repository.

Every tracked repository change must update `docs/FPL_APEX_MASTER_STATE.md` in the same change unless that ledger is the only tracked file changed. `scripts/check_master_state_sync.py` and CI enforce this requirement.

If this file, `AGENTS.md`, or supporting prose conflicts with `docs/APEX_V2_AUTHORITY.json` or immutable release evidence, machine/release authority wins and the prose must be corrected.
