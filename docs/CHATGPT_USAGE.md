# Using Apex V2 from ChatGPT

Canonical human continuity: [`FPL_APEX_MASTER_STATE.md`](FPL_APEX_MASTER_STATE.md). Machine authority: [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json). Human operating authority: [`APEX_OPERATING_MANUAL.md`](APEX_OPERATING_MANUAL.md).

Immutable forensic base (`frozen_engine_sha`): `99cc7b51b0cff45462b567084cb1844cfe0a456f`

Current serving core: read `production_core_sha` from `APEX_V2_AUTHORITY.json`.

The immutable base anchors PR #90/lineage and is not a serving-code pointer. The sole serving production workflow is `.github/workflows/apex-v2-daily-production.yml`; **AIrsenal** is the sole serving provider H1–H8. Research output is non-serving and has `production_influence = NONE`.

## What ChatGPT should read first

For an Apex engineering or recommendation task:

1. `docs/FPL_APEX_MASTER_STATE.md` — canonical human/project continuity ledger: current closure status, engineering history, closed decisions, known traps and exact next steps.
2. `docs/APEX_V2_AUTHORITY.json` — machine-readable production constitution and current `production_core_sha`; this outranks prose.
3. `docs/CURRENT_STATE.md` — shorter current operational view.
4. `docs/APEX_MASTER_CONTEXT.md` — constitutional Project Brain context.
5. `docs/APEX_OPERATING_MANUAL.md` — execution/answer policy.
6. The relevant V2 operations/research runbook.
7. Live GitHub `main`, PR #90, current serving-core SHA and the relevant immutable Apex V2 release/workflow state.

Do not begin from `data/generated/pinnacle_latest.json`, `apex_latest.json`, an old GW1 team or remembered conversation picks. Those are historical V1/V1.5 surfaces and are not the current serving interface.

## ChatGPT Project bootstrap

For the **FPL Apex Team** ChatGPT Project, keep the Project instruction deliberately short rather than copying mutable state into ChatGPT memory. The recommended persistent instruction is:

> For every substantive FPL Apex task, treat `mcnuggets651/fpl-apex/docs/FPL_APEX_MASTER_STATE.md` as the canonical human continuity ledger and `docs/APEX_V2_AUTHORITY.json` as machine production authority. Read the master ledger first, then machine authority, then the referenced current-state/operating/runbook files, and verify live GitHub/release/workflow facts before acting. For owner-specific state, use the private `mcnuggets651/fpl` query boundary and its `FPL_APEX_PRIVATE_MASTER_STATE.md`; never reconstruct squad/prices/transfers from chat memory. Immutable evidence and machine authority outrank prose and Project memory.

This makes Project memory a **navigation/cache layer**, not a competing source of truth. If the Project supports attached files, attaching or linking the public master ledger is useful for discovery, but a copied attachment can become stale; the live repository version remains canonical. Only attach the private companion in an owner-private Project where its contents are appropriate to expose.

Repository-side enforcement does not depend on ChatGPT remembering this instruction: root `AGENTS.md` / `CLAUDE.md` require the same preflight, and required CI rejects tracked changes that omit the master-state update.

## Current recommendation gate

A current Apex production verdict requires an immutable final produced by the authenticated Apex V2 production chain for entry **63984** using the exact authority-declared `production_core_sha`. Verify:

- immutable `frozen_engine_sha` lineage and current `production_core_sha` identity;
- current operations control-plane identity;
- exact authenticated manager state;
- current Official FPL authority/snapshot identity;
- qualified AIrsenal H1–H8 serving surface;
- successful exact solve/mechanics checks;
- immutable final publication identity, core provenance and freshness.

If any required serving gate fails, report the blocker. Do not choose manually between Pinnacle/Elite/shadow/research candidates and do not reconstruct a squad from memory.

## Production versus research

Use these labels consistently:

- **Apex production verdict** — immutable result from `.github/workflows/apex-v2-daily-production.yml` under the exact authority-declared serving core.
- **operations** — auth, deadline dispatch and evaluation controllers around the serving core and immutable base.
- **shadow/research** — prospective tournament, Decision Quality and provider diagnostics; never serving.
- **historical** — V1/V1.5/Pinnacle/Elite generated files and archived workflows.

A challenger forecast or a better realized counterfactual is evidence for review, not permission to blend or promote automatically.

## Natural interaction

Plain-language questions remain appropriate, for example:

- `What is the current Apex production recommendation?`
- `Roll or transfer this week?`
- `What are the XI, captain, vice and bench order?`
- `Show the H2–H3 tactical route and H4–H8 contingencies.`
- `Why is Player X above Player Y in the current production decision?`
- `Which serving assumptions are most fragile?`
- `What did the prospective tournament or Decision Quality lab learn, separately from production?`

For player comparisons, use current Official FPL facts, expected minutes/start/appearance probabilities, attacking/defensive/bonus components, fixture context, role/set-piece evidence and whole-squad opportunity cost from one coherent current snapshot. Do not mix numbers from different snapshots/model versions as if they were one run.

## Live research

External football research is appropriate when the repository has a concrete current evidence gap such as an injury, transfer, manager statement, lineup or role change. State the gap and preserve provenance/timing. External evidence cannot silently replace Official FPL identity or the authority-declared serving forecast constitution.

## GitHub interaction

For production, operate only the canonical V2 workflow or the bounded V2 deadline/auth controls documented in `APEX_V2_DAILY_OPERATIONS.md`. The retired `pinnacle.yml`, `airsenal.yml`, `refresh-core-pin.yml` and `gw1-final-2026.yml` files are archived under `archive/workflows/` and are intentionally inert.

Decision Quality and the prospective tournament are research workflows. Their successful completion does not create a second Apex team.

## Failure rule

When live immutable production state is unavailable, say exactly what is missing and withhold an invented Apex-labelled recommendation. The system is designed to fail closed rather than make a stale artifact look current.
