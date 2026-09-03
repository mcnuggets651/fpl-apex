# Using Apex V2 from ChatGPT

Machine authority: [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json). Human operating authority: [`APEX_OPERATING_MANUAL.md`](APEX_OPERATING_MANUAL.md).

Immutable forensic base (`frozen_engine_sha`): `99cc7b51b0cff45462b567084cb1844cfe0a456f`

Current serving core (`production_core_sha`): `40ac0176ebdf0ce7db80b77b31dbf19623d57932`

The immutable base anchors PR #90/lineage and is not a serving-code pointer. The sole serving production workflow is `.github/workflows/apex-v2-daily-production.yml`; **AIrsenal** is the sole serving provider H1–H8. Research output is non-serving and has `production_influence = NONE`.

## What ChatGPT should read first

For an Apex engineering or recommendation task:

1. `docs/APEX_V2_AUTHORITY.json` — machine-readable production constitution and current `production_core_sha`.
2. `docs/CURRENT_STATE.md` — current operational state and live acceptance gates.
3. `docs/APEX_MASTER_CONTEXT.md` — Project Brain.
4. `docs/APEX_OPERATING_MANUAL.md` — execution/answer policy.
5. The relevant V2 operations/research runbook.
6. Live GitHub `main`, PR #90, current serving-core SHA and the relevant immutable Apex V2 release/workflow state.

Do not begin from `data/generated/pinnacle_latest.json`, `apex_latest.json`, an old GW1 team or remembered conversation picks. Those are historical V1/V1.5 surfaces and are not the current serving interface.

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
