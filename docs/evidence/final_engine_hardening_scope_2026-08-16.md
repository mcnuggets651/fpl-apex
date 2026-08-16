# Final engine hardening scope — 2026-08-16

## Objective

Make PR #64 the final launch architecture/hardening pass for Apex. The goal is not another feature cycle; it is to remove the remaining authority/provenance seams so normal operation becomes data refresh + deadline re-solve.

## Repository audit conclusion

The existence of 63 historical PRs does not itself confuse the runtime. Git history is inert. Risk comes only from code, configuration, documentation and workflows that remain reachable from current `main`.

The audit identified the following material seams.

### 1. Fabricated set-piece shares

Official FPL ordinal set-piece order was converted to literal shares (`1 -> 1.00`, `2 -> 0.45`, `3 -> 0.15`) and added to xP. This affected the whole player pool, not only Kevin Schade.

Correction: ordinal rank remains context only. Literal share can enter production only from an explicit current sourced override. Any unexplained additive set-piece xP blocks the all-player truth gate.

### 2. Intermediate static team could become actionable

The base canonical builder previously published `exact_horizon_maximum_ev` with `ready_to_act=true`, then the adaptive strategy script overwrote it. Production fail-close protected most workflows, but this created a transient second authority and made standalone use unsafe.

Correction: the base builder is staging-only. It can set `strategy_base_ready=true`, but must always write `ready_to_act=false` and `recommendation=null`. Static exact-horizon output is retained only under internal diagnostics.

### 3. Final evidence could describe the wrong 15

Pinnacle built selected-player evidence for its static exact-horizon diagnostic squad before the adaptive selector chose the actual published 15. On a live production surface, only 12/15 final players overlapped the old dossier.

Correction: after the final adaptive/receding selector, Apex rebuilds selected-player evidence for the exact final 15, XI and captain. Dossier IDs must equal final squad IDs before publication.

### 4. Answer explanations used superseded static-selection logic

The answer context described final players as selected by the authoritative exact-horizon Decision and attached static force/ban regret even when the actual selector was adaptive.

Correction: explanations are selector-aware. Adaptive picks are explained by GW1-first policy; in-season picks by current-team receding horizon. Static exact-horizon per-player regret is diagnostic and cannot be presented as causal evidence for final picks.

### 5. Required expert coverage could silently vary by player

AIrsenal is a required projection expert, but the configured coverage floor was 95%. Missing player rows could therefore cause the ensemble to renormalise source weights for only some players.

Correction: required AIrsenal player/Gameweek xP coverage is 100%. Current production already supplies the complete 587 x 8 surface. FPL Core required player-ID coverage is also raised to 100%.

### 6. FPL Core current-season longitudinal shape

FPL Core playerstats becomes longitudinal as Gameweeks accumulate. Current reconciliation would otherwise create duplicate official player rows after multiple snapshots.

Correction: current production reconciliation selects the latest unambiguous player/GW snapshot per player. Ambiguous duplicate player/GW rows fail closed. Raw longitudinal history remains available outside current reconciliation.

### 7. Documentation contradicted the live EV-first/adaptive engine

The canonical policy/architecture still described static exact-horizon selection as production authority. The operating manual also retained a high-uncertainty evidence rule that contradicted the live adverse-evidence-only eligibility policy.

Correction: docs are part of the governed contract. They now describe the two final selectors and preserve the EV-first rule: forecast uncertainty is priced into xP; only attributable adverse/contradictory evidence can make XI/captain ineligible.

### 8. Workflow archaeology remained on the active execution surface

GitHub retained 28 historical workflow registrations in the Actions UI, while the current repository tree still contained 17 executable workflow YAMLs. Several were promotion-era or superseded one-off audits. Repeated surgical commits also started multiple expensive PR audits without per-PR cancellation, creating a large queue of obsolete runs.

Correction: six superseded workflows are moved intact to `archive/workflows/` and removed from `.github/workflows`, leaving an explicit 11-workflow governed active surface. The permanent expensive PR audits use per-PR/ref concurrency with `cancel-in-progress: true`, so only the newest relevant commit remains live. GitHub may continue to display historical workflow registrations/runs; those are history, not executable repository state.

## Frozen final production chain

1. Official FPL canonical universe.
2. Validated enrichment + forecasts.
3. Canonical ensemble `xp`.
4. Sealed decision bundle.
5. Internal Pinnacle/Elite/exact-horizon diagnostics.
6. Non-actionable staging packet.
7. All-player truth gate.
8. Exactly one final selector:
   - `adaptive_gw1_launch_with_transfer_option_value` before GW1;
   - `receding_horizon_current_team_maximum_ev` once a published team exists.
9. Exact current-GW mechanics.
10. Final selected-player evidence rebuilt for the actual 15/XI/captain.
11. Final answer-context gate.
12. `ready_to_act=true` only at step 12.

## Acceptance gates

- 100% Official FPL hard-fact coverage.
- unique official IDs.
- 100% FPL Core required player-ID coverage.
- 100% canonical player/Gameweek projection-pair coverage.
- 100% required AIrsenal xP player/Gameweek coverage.
- ordinal set-piece order never creates literal share by itself.
- unsourced set-piece share or unexplained set-piece xP fails closed.
- current FPL Core longitudinal rows reconcile to one unambiguous latest row per player.
- staging builder cannot publish a team.
- actionable selector is one of the two frozen final selectors only.
- final evidence dossier contains exactly the same 15 IDs as the canonical squad.
- captain and vice IDs reconcile to the final XI.
- answer reasons use the actual final selector.
- static exact-horizon regret is not attributed as causal evidence for adaptive/receding picks.
- active workflow tree equals the governed 11-workflow allowlist; superseded workflows remain archived outside `.github/workflows`.
- expensive permanent PR audits cancel superseded runs on the same PR/ref.
- CVaR, exact mechanics, parity and existing robustness gates remain unchanged; no scenario-count or tolerance weakening.
- fresh run on current `main` data pins must pass before merge approval is requested.

## Post-merge architecture freeze

After fresh production acceptance, routine work is source refresh, current-season evidence ingestion, deadline re-solving and no-hindsight learning. Do not create another architecture PR merely because a pick looks surprising or a single Gameweek goes badly.

Reopen architecture only for a reproducible contract defect, an upstream schema/semantics break, or a bounded challenger that demonstrates superior predictive and decision-level validity under existing promotion gates.
