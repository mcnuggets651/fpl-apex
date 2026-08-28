# Final production authority cutover — 2026-08-28

**Status: permanent production architecture, not degraded mode.**

Authority is now intentionally separated:

1. **Official FPL — factual truth.** Identity, club, position, price, availability, fixtures and mechanics are hard production facts.
2. **AIrsenal — production statistical xP.** Canonical `xp` is AIrsenal exactly; no subjective rescaling, averaging or Apex fallback is allowed. Missing/stale canonical AIrsenal blocks production.
3. **Understat + FPL Core — enrichment.** They retain historical priors, underlying stats, team strength, preseason/Elo/DefCon and shadow-model value. Their failures are explicit warnings unless a future promoted production model actually depends on them.
4. **Current football evidence — availability/minutes/role context.** Hard evidence can exclude or invalidate; soft evidence drives uncertainty/scenarios and does not manufacture point bonuses.
5. **Apex optimiser — decision authority.** Exact FPL mechanics, max-EV selection, near-equivalent robustness, captaincy, bench/autosubs and receding-horizon planning remain Apex's production job.
6. **Apex proprietary xP + reproducible challengers — shadow.** Their forecasts are retained and disagreement is visible, but they cannot alter canonical xP before promotion.
7. **Prospective calibration — judge.** Forecasts are frozen before deadlines; completed outcomes are scored out of sample. Promotion requires at least 8 genuine completed GWs, >=200 active rows, chronological holdouts, Gameweek-block bootstrap confidence, cohort diagnostics and explicit review. No automatic promotion occurs.

Production blockers follow the actual dependency graph. Optional research/enrichment failure cannot masquerade as a production failure; hard factual/canonical/mechanics/publication failures remain fail-closed. Future ensemble weights, if any, must be learned from genuine prospective frozen forecasts rather than hand selected.

# Apex FPL — Canonical Decision Policy

This document defines the **only user-facing team-selection policy** for Apex. Internal models and diagnostics may disagree, but they never create a second recommendation.

## Canonical contract

The only published/user-facing recommendation is:

- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`
- `data/generated/apex_answer_context.json`

The only production command is:

```bash
python scripts/run_apex.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
```

`pinnacle_latest.*`, `elite_latest.*`, CVaR, solver parity, exact-horizon frontiers and regret reports are **internal diagnostic/challenger evidence only**. They must never be presented as competing Apex teams.

## One-way decision hierarchy

1. Build the current canonical player/fixture universe from Official FPL.
2. Reconcile and enrich every official player with validated FPL Core, AIrsenal, historical, preseason, tactical, news and fixture evidence.
3. Produce the canonical ensemble expected-points surface (`xp`).
4. Seal that exact surface, evidence lineage, settings, upstream pins and team state into one decision bundle.
5. Run the static exact-horizon shortlist, exact mechanics, CVaR, regret, parity and Elite layers as internal diagnostics.
6. Assemble a **non-actionable staging packet**. At this point `ready_to_act=false` and `recommendation=null` by design.
7. Run the all-player truth gate over 100% of the Official FPL universe. Hard facts and required player/Gameweek forecast coverage must be complete; ordinal set-piece order may not masquerade as a literal share.
8. Apply exactly one final strategy selector:
   - before GW1: `adaptive_gw1_launch_with_transfer_option_value`;
   - after GW1/current-team state exists: `receding_horizon_current_team_maximum_ev`.
9. Resolve exact current-Gameweek XI, captain, vice-captain and bench mechanics for that final 15.
10. Rebuild the selected-player evidence dossier for **that exact final XV/XI/captain**, not for an earlier diagnostic squad.
11. Build `apex_answer_context.json` from the final selector, all-player truth result and final evidence identities.
12. Only if every final gate passes may Apex set `ready_to_act=true`.

No other script or selector may create an actionable canonical team.

## Pre-GW1 selector

`adaptive_gw1_launch_with_transfer_option_value` is deliberately GW1-first.

- Exact GW1 expected points are the primary launch objective.
- The best exact GW1 squad defines the ceiling.
- Only squads inside the configured near-equivalent GW1 tolerance may remain eligible.
- Future legal transfer option value may break ties/near-ties inside that band.
- Future transfer paths are contingencies, not commitments.
- Current prices are used; speculative future price changes are not invented.

This prevents the old error of selecting a frozen 15 merely because it looks best over eight held Gameweeks.

## In-season selector

`receding_horizon_current_team_maximum_ev` starts from the manager's actual permanent squad, bank, selling prices and free-transfer balance.

- The full legal future path may be solved for option value.
- Only the freshly solved **first action** is executable.
- The resulting current-Gameweek 15 is exact-rescored for XI, captain, vice and autosubs.
- Later moves are contingencies and must be rebuilt after new matches, injuries, transfers, roles, prices and news.

## Static exact-horizon diagnostics

The historical `authoritative_decision` key inside Pinnacle is retained for compatibility with existing diagnostic code. Its authority is now **local to the Pinnacle diagnostic layer only**. It cannot set `ready_to_act=true`, cannot own the final squad and cannot be used as the causal explanation for an adaptive/receding-horizon player selection.

## All-player truth contract

For every current Official FPL player:

- official ID, name, club, FPL position, price and status must be complete;
- Official FPL identity is canonical;
- required player/Gameweek projection pairs must be complete;
- required AIrsenal player/Gameweek xP coverage must be complete;
- FPL Core must account for every official player ID;
- mutable sourced overrides require attributable provenance and freshness;
- set-piece order is ordinal evidence only;
- literal set-piece shares require explicit current sourced evidence;
- future minutes, starting roles and xP remain forecasts and must be labelled as such.

Unknown future information remains uncertain; Apex must never manufacture precision to fill a gap.

## Evidence eligibility is EV-first

Expected minutes, start probability, appearance probability and role uncertainty are already inputs to expected value. They are **not** converted into a second hidden safety preference.

A player may be excluded from XI/captain eligibility only by attributable adverse evidence such as official adverse status, decision-grade negative evidence or an unresolved current contradiction. Mere numerical uncertainty does not make a higher-EV player ineligible.

## What does not enter the maximum-points objective

- ownership / effective ownership;
- reputation or popularity;
- a standalone value/points-per-million score;
- a standalone weighted Elite score;
- arbitrary minutes-certainty bonuses;
- independent random-player Monte Carlo noise.

Ownership belongs only in an explicitly different rank-management objective, never in the pure maximum-points recommendation.

## Promotion rule for future model changes

After the architecture freeze, a forecast/model change is not promoted because it looks plausible. It requires a bounded challenger, no-hindsight/out-of-sample evidence where available, decision-level impact analysis and explicit governance approval. Player-specific hand tuning is prohibited.

## ChatGPT operating rule

When the user asks for “the Apex team”, “best team”, “recommendation”, or equivalent:

1. Load `data/generated/apex_answer_context.json`.
2. If `safe_to_act` is false, report the blockers instead of inventing a team.
3. If true, present `production_result` as **the** Apex recommendation.
4. Explain selections using the final selector and `final_selected_player_evidence` only.
5. Use static exact-horizon/Pinnacle/Elite/CVaR outputs only to explain diagnostics or fragility.
6. Show a forced scenario only when explicitly requested, and label it as a scenario rather than a second recommendation.
