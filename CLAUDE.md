# Claude / AI Maintainer Instructions — FPL Apex

The mandatory repository contract is `AGENTS.md`.

Before doing substantive work, read completely:

1. `docs/FPL_APEX_MASTER_STATE.md`
2. `docs/APEX_V2_AUTHORITY.json`
3. `docs/CURRENT_STATE.md`
4. `docs/APEX_OPERATING_MANUAL.md`
5. `docs/APEX_CAPABILITY_REGISTRY.yaml`
6. `docs/APEX_ARCHITECTURE.md`
7. the relevant capability runbook/tests referenced by the registry

Then verify live GitHub/release/workflow facts before relying on mutable state.

Before a repository change, identify and declare the affected `Apex-Capabilities` from the registry. The PR must state authority impact, invariant impact and any reopened decisions. `scripts/check_capability_registry.py` compares that semantic declaration with the actual diff and rejects silent workflows/scripts or serving/research boundary drift.

Do not restart architecture design, merge/advance frozen PR #90, reconstruct owner state from memory, let research influence production implicitly, rerun optimisation in publication, weaken deterministic/integrity gates, put private manager/auth material in the public repository, or turn the capability registry/system map into a second live-state authority.

Every tracked repository change must update `docs/FPL_APEX_MASTER_STATE.md` in the same change unless that ledger is the only tracked file changed. `scripts/check_master_state_sync.py` and CI enforce this requirement.

`docs/APEX_DECISIONS.md` remains append-only rationale/history; `docs/APEX_DECISION_INDEX.yaml` records machine-readable active/superseded status. Do not rewrite old rationale merely because V2 superseded its authority.

If this file, `AGENTS.md`, the registry, system map or supporting prose conflicts with `docs/APEX_V2_AUTHORITY.json` or immutable release evidence, machine/release authority wins and the subordinate documentation must be corrected in the same change.
