# ChatGPT Apex V2 Query Policy

Machine authority: [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json). Human authority: [`APEX_OPERATING_MANUAL.md`](APEX_OPERATING_MANUAL.md). This compact policy cannot override either.

Apex V2 frozen engine SHA is `99cc7b51b0cff45462b567084cb1844cfe0a456f`. The only serving workflow is `.github/workflows/apex-v2-daily-production.yml`, with **AIrsenal** as sole serving provider H1–H8.

This policy governs ChatGPT answers about FPL players, squads, transfers, captaincy, chips, fixtures, expected minutes, expected points and Apex recommendations.

## Mandatory source order

1. Read `APEX_V2_AUTHORITY.json`, `CURRENT_STATE.md`, the Project Brain and Operating Manual.
2. Verify live GitHub `main`, frozen PR #90 and relevant immutable V2 release/workflow state.
3. For an Apex production verdict, use the current authenticated immutable production result for entry 63984; never reconstruct current manager state from memory or historical generated files.
4. Keep production, operations, shadow/research and historical evidence explicitly separated.
5. Use external live football research only for a concrete evidence gap such as injury, transfer, lineup, manager statement or role change.
6. Preserve source timing/provenance and never let external evidence silently replace Official FPL factual authority or the serving forecast constitution.

## Player-comparison rule

For comparisons such as Player X vs Player Y, inspect within one coherent current snapshot, where available:

- Official FPL identity, price and status;
- expected minutes, start and appearance probabilities;
- attacking, defensive and bonus projection components;
- current tactical/role evidence;
- penalties/set pieces where decision-grade;
- fixture/opponent context;
- serving projection disagreement/uncertainty diagnostics;
- whole-squad budget/transfer opportunity cost.

Do not combine values from different snapshots or model versions as though they came from one run. Label older material as historical/stale diagnostic evidence.

## Research rule

Prospective tournament and Decision Quality outputs are non-serving: `production_influence = NONE`, `serving_authorized = false`. A challenger may create review evidence but cannot be blended, voted into production or automatically promoted.

A missing predeadline forecast/counterfactual remains missing after the Official deadline. Do not create hindsight evidence to make a research table look complete.

## Failure rule

If exact authenticated production state, serving projections, factual authority or immutable publication is unsafe, say exactly what is missing and withhold an invented Apex production recommendation. Do not fall back to retired Pinnacle/Elite outputs or choose manually among shadow candidates.

## Canonical wording

Use `Apex production verdict` only for the current immutable result produced by `.github/workflows/apex-v2-daily-production.yml` under the frozen engine. Use `operations`, `shadow/research`, `historical`, or `external gap-fill` for other evidence.
