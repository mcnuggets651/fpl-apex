# Apex FPL — Canonical Decision Policy — HISTORICAL PRE-V2

> **HISTORICAL / NON-SERVING CONTRACT**
>
> This document preserves the pre-V2 `scripts/run_apex.py` / generated-recommendation decision contract. It is **not current production authority**.
>
> Current V2 routing is:
> - machine authority: `docs/APEX_V2_AUTHORITY.json`;
> - human continuity: `docs/FPL_APEX_MASTER_STATE.md`;
> - capability/change-surface index: `docs/APEX_CAPABILITY_REGISTRY.yaml`;
> - current system map: `docs/APEX_ARCHITECTURE.md`;
> - manager-query contract: `docs/CHATGPT_APEX_QUERY_POLICY.md`.
>
> Decision D031 superseded the production-authority claims below. `scripts/run_apex.py`, `data/generated/apex_recommendation_latest.*`, `data/generated/apex_answer_context.json` and the Pinnacle/Elite/static-selector authority chain are historical/non-serving. The prose below is retained for forensic history and legacy-model research only.

## Historical canonical contract

The old published/user-facing recommendation was:

- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`
- `data/generated/apex_answer_context.json`

The old production command was:

```bash
python scripts/run_apex.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
```

`pinnacle_latest.*`, `elite_latest.*`, CVaR, solver parity, exact-horizon frontiers and regret reports were internal diagnostic/challenger evidence within that architecture.

## Historical one-way decision hierarchy

1. Build the canonical player/fixture universe from Official FPL.
2. Reconcile and enrich official players with the then-configured evidence stack.
3. Produce the old canonical ensemble expected-points surface (`xp`).
4. Seal that surface, evidence lineage, settings, upstream pins and team state into one decision bundle.
5. Run static exact-horizon shortlist, exact mechanics, CVaR, regret, parity and Elite layers as diagnostics.
6. Assemble a non-actionable staging packet.
7. Run the all-player truth gate.
8. Apply the then-final strategy selector.
9. Resolve exact current-Gameweek mechanics.
10. Rebuild selected-player evidence for the exact final squad.
11. Build the old `apex_answer_context.json`.
12. Only if every old final gate passed could that architecture set `ready_to_act=true`.

No part of this historical hierarchy overrides V2 machine authority.

## Historical pre-GW1 selector

`adaptive_gw1_launch_with_transfer_option_value` used exact GW1 expected points as the primary launch objective, with future legal transfer option value as a near-tie breaker.

## Historical in-season selector

`receding_horizon_current_team_maximum_ev` started from the manager's then-current permanent squad, bank, selling prices and free-transfer balance, executed only the first freshly solved action, and treated later moves as contingencies.

## Historical static diagnostics

The old `authoritative_decision` key inside Pinnacle had only local diagnostic meaning after later pre-V2 changes. Under V2 even that surrounding production chain is historical/non-serving.

## Historical all-player truth contract

The pre-V2 contract required complete Official identity facts, player/Gameweek projection coverage, required AIrsenal coverage, source provenance and separation of ordinal set-piece order from literal shares.

## Historical evidence-eligibility principle

Expected minutes, start probability, appearance probability and role uncertainty were intended to enter expected value rather than a second hidden safety preference. This modelling principle may remain useful as historical context, but the authority-selected V2 core is the implementation authority.

## Historical objective exclusions

The old maximum-points objective excluded ownership/effective ownership, standalone value scores, standalone Elite utility, arbitrary minutes-certainty bonuses and independent random-player noise unless an explicitly different objective was being studied.

## Historical promotion rule

Model changes were expected to earn promotion through bounded challenger evidence, no-hindsight/out-of-sample evidence where available, decision-level analysis and explicit governance approval. V2 promotion/serving authority is now controlled by `docs/APEX_V2_AUTHORITY.json` and the current governance process.

## Current ChatGPT rule

Do **not** follow the old instruction to read generated recommendation files as current authority.

When the user asks for the current Apex team, transfer or strategy:

1. read `docs/FPL_APEX_MASTER_STATE.md` and `docs/APEX_V2_AUTHORITY.json`;
2. verify current immutable/live authority state;
3. use `docs/CHATGPT_APEX_QUERY_POLICY.md` and the approved private `mcnuggets651/fpl` query boundary for owner-specific state;
4. fail closed/report a refresh blocker rather than reconstructing manager state from memory or this historical document;
5. keep research/shadow evidence explicitly non-serving.
