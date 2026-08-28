# Apex FPL — Canonical Decision Policy

This document defines the **only user-facing team/action-selection policy** for Apex. Internal forecasts and diagnostics may disagree, but they never create a second recommendation.

## Canonical files

The only published/user-facing decision contract is:

- `data/generated/apex_answer_context.json`
- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`

The production entrypoint is:

```bash
python scripts/run_apex.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
```

If the current answer context is not safe/actionable, Apex has **no recommendation**. Historical squads, `pinnacle_latest.*`, `elite_latest.*`, old `apex_latest.*` files and conversation memory are not fallback authority.

## Forecast authority

Production statistical expected points are supplied by **AIrsenal**.

In the production configuration:

- canonical `xp` equals validated `airsenal_xp` exactly;
- Official FPL remains factual rather than statistical xP authority;
- Apex proprietary xP is shadow-only;
- FPL Core and Understat are enrichment/shadow sources;
- no subjective fixed blend is permitted;
- missing/stale/incomplete AIrsenal coverage blocks production rather than falling back to Apex.

Any future ensemble or alternate provider must be promoted through prospective evidence and explicit governance. Production weights must not be hand-selected to obtain a preferred squad.

## One-way decision hierarchy

1. Acquire and seal the current Official FPL player/fixture universe.
2. Validate complete fresh AIrsenal player/Gameweek projection coverage for the governed horizon.
3. Ingest current football evidence and optional enrichment with explicit provenance/health.
4. Build one canonical projection/evidence/team-state surface.
5. Seal it into one DecisionBundle.
6. Run static exact-horizon, CVaR, regret, parity and Elite surfaces as diagnostics on that same bundle.
7. Assemble a non-actionable staging packet (`ready_to_act=false`, `recommendation=null`).
8. Run all-player factual/projection truth checks.
9. Apply exactly one final strategy selector:
   - historical pre-GW1: `adaptive_gw1_launch_with_transfer_option_value`;
   - current in-season: `receding_horizon_current_team_maximum_ev`.
10. Resolve exact current-Gameweek XI, captain, vice-captain, bench and autosub mechanics.
11. Rebuild evidence for the actual selected 15/action.
12. Build `apex_answer_context.json` and expose a recommendation only when every required final gate passes.

No other path may set `ready_to_act=true`.

## Current in-season selector

GW1 is complete. Normal production now uses `receding_horizon_current_team_maximum_ev`.

It starts from the manager's actual permanent squad, bank, realised selling values and free-transfer state. The engine may solve a longer legal path to value future flexibility, but only the freshly solved **first action** is executable. Future moves are contingencies and must be rebuilt after new prices, matches, injuries, transfers and role information.

## Historical pre-GW1 selector

`adaptive_gw1_launch_with_transfer_option_value` remains retained for replay/history. It is GW1-first: exact launch expected points define the primary ceiling, and future transfer option value may differentiate only near-equivalent launch squads. The expired one-off GW1 production workflow is archived and this selector is not the current live mode.

## Static diagnostic surfaces

Pinnacle/static exact-horizon, Elite, CVaR, force/ban regret, captain stability and independent parity are internal evidence layers. They may challenge fragility or implementation, but they cannot publish a competing team or silently substitute a different objective.

## All-player truth contract

For every current Official FPL player, production requires:

- unique Official ID;
- complete current name/club/FPL-position/price/status factual mapping;
- complete canonical player/Gameweek projection coverage;
- complete required AIrsenal player/Gameweek coverage;
- no identity conflict silently resolved against Official FPL;
- explicit provenance/classification for decision-sensitive overrides;
- no unsourced literal set-piece shares.

FPL Core no longer has to cover every current Official ID for production readiness because it is enrichment rather than canonical-xP authority. Its coverage remains monitored and disclosed.

## Evidence eligibility is EV-first

The production eligibility policy is **adverse-evidence-only** before solve.

Expected minutes, start probability, appearance probability and role uncertainty are already forecast inputs. They must not be converted into a second hidden preference for supposedly safer players.

A player may be made XI/captain-ineligible only by attributable adverse evidence such as Official adverse status/suspension, decision-grade negative evidence or an unresolved material current contradiction. Numerical uncertainty by itself is diagnostic rather than exclusionary.

## What does not enter the pure maximum-points objective

- ownership/effective ownership;
- reputation/popularity;
- standalone points-per-million/value scores;
- standalone Elite score;
- arbitrary minutes-security bonuses;
- manually remembered prices or player roles;
- subjective forecast-provider weights.

## Promotion rule

A forecast/model/provider change is not promoted because it looks plausible or produces a preferred player. It requires a frozen challenger, genuine no-hindsight prospective outcomes, governed evaluation, decision-level impact analysis and explicit approval. Current governance requires at least 8 genuine completed Gameweeks and >=200 active rows before production promotion can be considered.

## ChatGPT operating rule

When asked for “the Apex team”, “best team”, “transfer”, or equivalent:

1. Load `data/generated/apex_answer_context.json`.
2. Verify freshness, bundle/snapshot identity, source health, all-player truth, solver/parity, exact mechanics and final evidence identity.
3. If `safe_to_act=false` or `ready_to_act=false`, report blockers and **do not invent a team**.
4. If actionable, present `production_result` as the one Apex recommendation.
5. Explain selections using the final selector and final selected-player evidence.
6. Show forced alternatives only when explicitly requested and label them as scenarios.
