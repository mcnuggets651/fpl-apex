# Apex FPL — Architecture

## Production authority architecture — 28 August 2026

This is the permanent V1 production authority layout after the forecast cutover. It is not a degraded fallback mode.

```text
Official FPL
(factual truth: IDs / clubs / FPL positions / prices / status / fixtures)
        |
        +------------------------------+
        |                              |
        v                              v
Fresh validated AIrsenal         Enrichment + evidence
canonical statistical xP         FPL Core / Understat / history /
        |                        current news, roles, minutes context
        |                              |
        +---------------+--------------+
                        |
                        v
                Sealed decision bundle
      (Official truth + AIrsenal xP + evidence + team state + provenance)
                        |
                        v
                 Apex decision engine
       (legal optimisation / exact mechanics / parity /
          captain / vice / bench / autosubs / receding horizon)
                        |
                        v
              Final selected-player evidence
                        |
                        v
                Apex answer-context gate
                        |
                        v
             ONE USER-FACING RECOMMENDATION
```

Parallel to production:

```text
Apex proprietary xP / Understat-based variants / OpenFPL-style challengers
                        |
                        v
                  SHADOW FORECASTS
                        |
                        v
        immutable prospective deadline ledger
                        |
                        v
         realised Official outcome evaluation
                        |
                        v
       governed promotion / rejection decision
```

## Layer responsibilities

### 1. Official FPL factual universe

Official FPL is absolute current authority for:

- Official player ID;
- club/team;
- FPL position;
- current price;
- Official availability/status fields;
- fixture identity/schedule;
- manager-neutral current FPL universe and rules inputs.

External sources may enrich or challenge a forecast, but may not silently rewrite current Official identity or price facts. All-player factual integrity is release-blocking.

### 2. Canonical statistical projection

AIrsenal is the sole production statistical xP provider until a challenger earns promotion from genuine prospective evidence.

In production authority mode:

- `xp == production_xp == airsenal_xp`;
- AIrsenal is not subjectively rescaled;
- Apex xP is retained as `apex_shadow_xp`;
- missing/stale/incomplete AIrsenal does **not** fall back to Apex;
- complete current Official-player × horizon coverage is required.

The legacy fixed three-way blend is retired from production. Research configurations may still exercise legacy blending mechanics for regression/challenger work, but those configurations are not production authority.

### 3. FPL Core enrichment

FPL Core remains valuable for current/historical player statistics, preseason evidence, Elo/team context, defensive contributions and other supporting features. It is pinned only after semantic/identity validation.

FPL Core health is visible in the answer context. Its failure is an enrichment warning while canonical AIrsenal xP is independent of it. If a future promoted production forecast explicitly depends on Core, dependency criticality must be changed as part of that promotion.

### 4. Understat enrichment and shadow modelling

Understat remains useful for underlying-stat priors, player/team research and Apex shadow models. An HTTP-success response with empty football payload is explicitly unhealthy.

Understat does not currently own canonical xP and cannot block production merely because its optional enrichment path is unavailable. A future production dependency requires prospective promotion evidence and an explicit dependency change.

### 5. Current football evidence

Injuries, suspensions, transfers, manager comments, role evidence, lineups and set-piece evidence have bounded roles and provenance.

The eligibility policy is EV-first / adverse-evidence-only:

- official adverse availability or suspension can hard-block eligibility;
- decision-grade negative role/availability evidence can constrain eligibility;
- unresolved material contradictions can block;
- ordinary uncertainty is priced in forecasts/scenarios rather than converted into a second hidden conservative preference;
- ordinal set-piece hierarchy may not be converted into invented literal shares.

### 6. Sealed decision bundle

The production solve seals the current player/fixture truth, projection surface, evidence, settings, upstream identity and manager state into one content-addressed bundle. Optimisers and diagnostics must operate on that same surface rather than independently refetching live data.

### 7. Apex optimiser and exact mechanics

Apex remains the production **decision** authority even though it is no longer the production **forecast** authority.

Apex owns:

- legal budget/club/position constraints;
- exact current manager-state finance where applicable;
- transfer/roll/hit decisions;
- current XI;
- captain and vice-captain;
- ordered bench and autosub mechanics;
- exact current-Gameweek rescoring;
- independent solver parity;
- correlated robustness/regret diagnostics;
- receding-horizon option value and first-action publication.

### 8. Strategy selectors

There are exactly two retained final selectors:

- historical/pre-GW1: `adaptive_gw1_launch_with_transfer_option_value`;
- current/in-season: `receding_horizon_current_team_maximum_ev`.

GW1 is complete; normal operation is now the receding-horizon current-team mode. The pre-GW1 selector remains for replay/history only.

The static exact-horizon solver, Pinnacle, Elite, CVaR and regret surfaces are diagnostics. They cannot independently set `ready_to_act=true`.

### 9. Final evidence and answer context

After the actual final 15/action is chosen, evidence is rebuilt for that exact selection. Evidence attached to an earlier diagnostic squad cannot satisfy publication.

The only user-facing authority is `data/generated/apex_answer_context.json`. A recommendation is exposed only when the final contract is safe/actionable.

## Production readiness gates

Production remains fail-closed for real dependencies, including:

- stale/mismatched Official FPL truth;
- incomplete current Official player factual coverage;
- stale/unhealthy/incomplete AIrsenal production projection coverage;
- invalid manager state or price/selling-value mechanics when required;
- invalid evidence/provenance where the decision depends on it;
- invalid DecisionBundle identity;
- non-optimal/inconclusive required solver surfaces;
- failed independent parity;
- invalid exact current-Gameweek mechanics;
- final evidence identity mismatch;
- publication/answer-context inconsistency.

FPL Core, Understat and internal fixture/model enrichments are warnings rather than hard production blockers unless a promoted production component explicitly depends on them.

## Prospective learning and promotion

Production and shadow forecasts must be frozen before deadlines with provider/version/snapshot/player/GW identity. Outcomes are joined only after the event.

The current promotion contract requires at least:

- 8 completed genuine prospective Gameweeks;
- 200 active evaluation rows;
- chronological/walk-forward comparison;
- Gameweek-block uncertainty/confidence analysis;
- cohort diagnostics and source ablation where relevant;
- explicit review.

No automatic promotion is allowed. At the 28 August audit the genuine calibration archive still contained zero completed Gameweeks, so Apex proprietary xP has no production forecast authority.

## Architecture freeze

After the authority cutover, routine work is not continuous redesign. Normal operation is:

- acquire fresh Official truth;
- refresh AIrsenal;
- refresh/validate enrichment sources;
- collect current football evidence;
- solve the current legal action;
- publish only through the canonical answer contract;
- archive predictions/decisions before deadlines;
- evaluate them after outcomes.

Architecture reopens only for a reproducible contract defect, an upstream semantic change that cannot be reconciled safely, or a challenger that passes the established prospective promotion gates.

## V2 boundary

The stacked V2 PR programme remains separate and withheld. It cannot inherit production authority merely because its engineering mechanisms are green. Its latest stack still contains documentation/config assumptions tied to the retired fixed forecast blend and therefore requires rebase and requalification before future cutover.
