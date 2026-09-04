# FPL Apex Project Brain

This directory is the public continuity/documentation layer for FPL Apex. It is **not** a second serving authority.

## Mandatory read order for every new Apex session

1. [`FPL_APEX_MASTER_STATE.md`](FPL_APEX_MASTER_STATE.md) — canonical human/project continuity ledger.
2. [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json) — machine serving authority; it outranks prose.
3. [`CURRENT_STATE.md`](CURRENT_STATE.md) and [`APEX_OPERATING_MANUAL.md`](APEX_OPERATING_MANUAL.md) — current supporting status and operating protocol.
4. [`APEX_CAPABILITY_REGISTRY.yaml`](APEX_CAPABILITY_REGISTRY.yaml) — canonical semantic capability/change-surface index.
5. [`APEX_ARCHITECTURE.md`](APEX_ARCHITECTURE.md) — the single current cross-repository V2 system map.
6. The specific capability runbook/tests referenced by the registry for the surface being touched.
7. Verify live GitHub, immutable release/workflow state and Official FPL facts before relying on mutable state.
8. For owner-specific squad/transfer questions, use the approved private `mcnuggets651/fpl` query boundary. Never reconstruct owner state from memory or old generated files.

Do not reconstruct the project from chat memory when these sources are available.

## Authority and documentation roles

The permanent hierarchy is:

```text
Immutable evidence
  -> Machine authority
  -> Master state
  -> Capability registry
  -> Current system map
  -> Capability runbooks/contracts
  -> Decision history
  -> Code/tests
  -> Conversation memory
```

Each layer has one job:

- [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json): current machine serving constitution and movable production-core pointer.
- [`FPL_APEX_MASTER_STATE.md`](FPL_APEX_MASTER_STATE.md): dated continuity/status/evidence ledger.
- [`APEX_CAPABILITY_REGISTRY.yaml`](APEX_CAPABILITY_REGISTRY.yaml): stable capability IDs, entry points, dependencies, privacy, failure behavior, runbooks, tests and change surfaces.
- [`APEX_ARCHITECTURE.md`](APEX_ARCHITECTURE.md): current system relationships and public/private/production/research flows.
- [`APEX_DECISION_INDEX.yaml`](APEX_DECISION_INDEX.yaml): machine-readable status/supersession index for decisions.
- [`APEX_DECISIONS.md`](APEX_DECISIONS.md): append-only decision rationale/history.
- capability runbooks: bounded operational procedure.

The registry and architecture map deliberately do **not** copy current production-core SHAs, workflow run IDs, latest release identity, owner squad/bank/free transfers/prices, or live provider health. Those facts belong to machine authority, immutable evidence, the master state or the private query plane as appropriate.

## Current canonical documents

- [`FPL_APEX_MASTER_STATE.md`](FPL_APEX_MASTER_STATE.md) — canonical human continuity ledger.
- [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json) — machine production authority.
- [`APEX_CAPABILITY_REGISTRY.yaml`](APEX_CAPABILITY_REGISTRY.yaml) — capability registry and change-surface index.
- [`APEX_ARCHITECTURE.md`](APEX_ARCHITECTURE.md) — current V2 system map.
- [`APEX_DECISION_INDEX.yaml`](APEX_DECISION_INDEX.yaml) — decision status/supersession index.
- [`APEX_DECISIONS.md`](APEX_DECISIONS.md) — append-only decision history.
- [`CURRENT_STATE.md`](CURRENT_STATE.md) — supporting current-state summary; machine authority/master state outrank it.
- [`APEX_MASTER_CONTEXT.md`](APEX_MASTER_CONTEXT.md) — supporting project context.
- [`APEX_OPERATING_MANUAL.md`](APEX_OPERATING_MANUAL.md) — mandatory operating protocol.
- [`APEX_V2_DAILY_OPERATIONS.md`](APEX_V2_DAILY_OPERATIONS.md) — canonical V2 production/operations runbook.
- [`CHATGPT_APEX_QUERY_POLICY.md`](CHATGPT_APEX_QUERY_POLICY.md) — manager-query contract.
- [`APEX_V2_PROSPECTIVE_TOURNAMENT.md`](APEX_V2_PROSPECTIVE_TOURNAMENT.md) — prospective provider research runbook.
- [`operations/PARALLEL_DECISION_LAB.md`](operations/PARALLEL_DECISION_LAB.md) — Decision Quality research runbook.
- [`operations/SHADOW_PROVIDER_RELIABILITY.md`](operations/SHADOW_PROVIDER_RELIABILITY.md) — shadow-provider health/reliability runbook.
- [`APEX_CHANGELOG.md`](APEX_CHANGELOG.md) — project evolution by milestone/version.
- [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) — known limitations/unresolved risks.

## Historical / non-serving documents and surfaces

These may remain useful for forensics or old-model research, but they must not be used to determine current serving authority:

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — pre-V2 architecture.
- [`APEX_CANONICAL_DECISION_POLICY.md`](APEX_CANONICAL_DECISION_POLICY.md) — pre-V2 `scripts/run_apex.py` / generated recommendation contract.
- `scripts/run_apex.py` — historical V1/V1.5 runner.
- `data/generated/apex_recommendation_latest.*` and `data/generated/apex_answer_context.json` — historical generated repository recommendation surfaces.
- old Pinnacle/Elite/static-selector authority statements.
- retired publishers preserved under `archive/workflows/`.

Their status is machine-classified by the `legacy` section of `APEX_V2_AUTHORITY.json` and the `LEG-*` capabilities in the registry.

## Agent / maintainer protocol

When the user says **continue Apex**, asks for the Apex team, or asks to change the repository:

1. Follow the mandatory read order above.
2. Reconcile live facts with machine authority and immutable evidence.
3. For owner questions, invoke the private query boundary rather than reading a remembered/generated squad.
4. Distinguish production, operations, research and historical evidence explicitly.
5. Do not present research/shadow output as a second Apex recommendation.
6. Do not describe an unmerged idea as production.
7. Before changing the repository, identify the affected `Apex-Capabilities` from the registry and the required runbooks/tests.
8. Update `FPL_APEX_MASTER_STATE.md` in the same change as every tracked repository change unless the ledger is the only changed tracked file.
9. Record new architectural/governance decisions in `APEX_DECISIONS.md` and status/supersession in `APEX_DECISION_INDEX.yaml`.

## Change-surface enforcement

`scripts/check_capability_registry.py` validates that:

- every active workflow is owned by at least one registered capability;
- every operational `scripts/apex_v2_*.py` helper is registered;
- authority-ref entry points are resolved against the correct immutable ref rather than mutable `main` only;
- serving capabilities have authority/runbook/test/failure/runtime-acceptance contracts;
- active research capabilities explicitly have no serving authority, no production influence and no automatic promotion;
- historical/retired capabilities cannot silently regain serving authority;
- every changed path belongs to a registered capability change surface;
- PR `Apex-Capabilities` metadata matches the actual diff;
- the decision index covers the append-only prose decision register;
- the registry has not become a live-state dashboard by copying movable authority/state.

The checker is wired into existing Apex CI / V2 Ops Contract rather than creating a new required workflow.

This index exists specifically to prevent context drift, silent functionality and repeated rediscovery loops.
