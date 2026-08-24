# Apex FPL — Architecture

## Final system flow

```text
Official FPL API
      |
      v
Canonical player/fixture universe (100% official identities)
      |
      +--> FPL Core Insights
      +--> pinned AIrsenal
      +--> historical data
      +--> preseason observations
      +--> tactical-role inference
      +--> news / manager / transfer evidence
      +--> validated fixture / Understat team model
      |
      v
Minutes model + player-rate model + team/fixture environment
      |
      v
Apex xP decomposition
(minutes, attack, CS, saves, DEFCON, sourced set pieces, bonus/BPS)
      |
      v
Projection ensemble
(mean xP, expert contributions, disagreement, confidence, variance)
      |
      v
Sealed decision bundle
(content hashes, code/config, evidence, projections, team state)
      |
      v
INTERNAL DIAGNOSTICS ONLY
(static exact-horizon frontier, exact mechanics, CVaR, regret,
 captain stability, independent parity, Elite epsilon frontier)
      |
      v
Non-actionable staging packet
ready_to_act=false / recommendation=null
      |
      v
All-player truth gate
(100% facts + required player/GW coverage + provenance semantics)
      |
      +------------------------------+
      |                              |
      | pre-GW1                      | in season/current team
      v                              v
GW1-first adaptive selector     Current-team receding-horizon selector
`adaptive_gw1_launch_...`       `receding_horizon_current_team_...`
      |                              |
      +---------------+--------------+
                      |
                      v
Exact current-GW mechanics
(XI / captain / vice / bench / autosubs)
                      |
                      v
Rebuild evidence for the ACTUAL final 15 / XI / captain
                      |
                      v
Final answer-context gate
                      |
                      v
ONE USER-FACING OUTPUT
ready_to_act=true only here
```

## Layer responsibilities

### Canonical universe

Official FPL owns player identity, club, FPL position, price, status and fixture identity. External sources may enrich but cannot silently overwrite these fields. Every production run must account for the full current Official FPL player universe.

### Evidence ingestion

Sources have bounded roles. Current sourced overrides require attributable provenance, timestamps and expiry where appropriate. Source health does not by itself prove a player fact.

### FPL Core reconciliation

Current production consumes the latest unambiguous FPL Core player/Gameweek snapshot for each player when the upstream file becomes longitudinal. Raw longitudinal rows remain available to historical/backtest consumers. Ambiguous duplicate player/GW snapshots fail closed.

### Minutes model

Expected minutes, start probability, appearance probability and 60+/80+ probabilities are forecasts. They combine historical/current playing time, preseason participation, official availability and current evidence. They are expected-value inputs, not a standalone safety score.

### Player-rate model

Attacking/defensive rates use observed player evidence and validated shrinkage/blending rules. Set-piece hierarchy is not converted into a made-up probability. Ordinal FPL set-piece order is context; a literal current share requires separately sourced evidence. Any future redesigned penalty model must prove predictive value and avoid double counting historical xG before promotion.

### Team / fixture environment

Opponent and home/away conditions are produced by validated team-strength inputs. If an official strength field is unusable, only a previously validated fallback may enter production. Alternative models remain challengers until evidence supports promotion.

### Projection layer

Produces transparent player/Gameweek expected-point components. Forecast construction is separate from squad selection.

### Ensemble

Combines configured forecast experts into canonical `xp` while exposing exact expert contributions and disagreement. Required AIrsenal xP must cover every official player/Gameweek pair; missing required expert rows may not silently change weights for a subset of players.

### Sealed decision bundle

Ingestion and projection run once. Player universe, projection matrix, evidence lineage, source timestamps, settings, upstream pins and team state receive one content-addressed `bundle_id`. Every optimiser and diagnostic consumes that exact bundle.

### Internal static diagnostics

The static exact-horizon solver/frontier, Pinnacle CVaR, regret, independent solver parity and Elite epsilon frontier remain valuable diagnostics. The legacy `authoritative_decision` field inside Pinnacle is retained for compatibility, but it is **not production authority** after the adaptive strategy release.

The static horizon surface can answer questions such as fragility, alternative structures and solver agreement. It cannot publish a team.

### Non-actionable staging

`build_canonical_recommendation.py` validates that the diagnostic layers describe the same healthy sealed surface, then deliberately writes:

- `strategy_base_ready=true` when the base is healthy;
- `ready_to_act=false`;
- `recommendation=null`.

This removes the former transient second authority where a frozen eight-Gameweek team could briefly appear canonical before the adaptive selector overwrote it.

### All-player truth gate

Before final selection becomes actionable, every current Official FPL player is audited for:

- hard factual completeness;
- unique official identity;
- canonical projection-pair completeness;
- required AIrsenal player/Gameweek coverage;
- set-piece rank/share semantic separation;
- provenance of any explicit set-piece share;
- explicit classification of roles/minutes as facts, sourced overrides, inference or forecast.

Unknown future states remain forecasts rather than invented facts.

### GW1-first adaptive selector

Before the first deadline, the canonical selector is `adaptive_gw1_launch_with_transfer_option_value`.

1. Solve exact GW1 expected points.
2. Keep only launch squads inside the configured near-equivalent GW1 tolerance.
3. Use the legal future transfer path as option-value tie-break evidence inside that band.
4. Publish one launch 15 with exact GW1 mechanics.

The engine therefore starts with the strongest defensible GW1 team while still valuing transfer flexibility; it does not optimise a frozen eight-week hold.

### Receding-horizon in-season selector

Once a real published team state exists, the canonical selector is `receding_horizon_current_team_maximum_ev`.

It starts from the actual current squad, bank, selling prices and free transfers. The legal future path may be solved, but only the first action is executable. After that action, the current 15 is exact-rescored. Every later move is a contingency that is rebuilt at the next deadline.

### Final selected-player evidence

After the final selector chooses the actual 15, Apex rebuilds the selected-player evidence dossier against that exact squad/XI/captain. Evidence from an earlier static diagnostic squad cannot satisfy this gate. The dossier IDs must match the canonical 15 exactly.

### Evidence eligibility

The production eligibility policy is EV-first/adverse-evidence-only. Quantitative minutes or role uncertainty is already priced into expected points and does not impose a second conservative selection penalty. Only official adverse status, decision-grade negative evidence or a current unresolved contradiction may make a player XI/captain-ineligible.

### Robustness

CVaR, correlated scenarios, regret and parity quantify fragility. They remain diagnostics and never silently substitute a different objective for expected FPL points.

### Learning

Learning is an offline, immutable and no-hindsight process. The sealed production runtime does not retrain itself and a live evaluation cannot mutate a champion.

Each learning chain separates:

1. an immutable `ModelTrainingRun` with training cutoff, first-available time, datasets, trainer code and parameter artifacts;
2. an `EvaluationDataset` whose predictions were sealed before later post-event truth became available;
3. an exact `EvaluationObservationSet` whose actual outcomes remain complete even when a model explicitly lacks a prediction;
4. a truth-governed `ModelEvaluationReport` using only VERIFIED targets from `OutcomeTruthRegistry`;
5. a candidate/incumbent `ModelComparisonReport` over the identical model-independent source truth set **and** identical normalized realized truth set;
6. a separate `ModelPromotionCertificate` applying predeclared exact promotion rules under the registered qualified champion learning policy;
7. an immutable parent-linked `ModelRegistryGeneration` changed only by a stale-writer-safe CAS transition.

Durable learning metrics and thresholds use exact rational values. SHADOW and PRODUCTION learning evidence have different semantic identity. Unresolved targets remain INCONCLUSIVE; for example, START truth is not inferred from minutes. A valid but unrelated artifact cannot satisfy a learning dependency merely because its SHA exists: downstream learning stages replay exact object type, semantic identity and retained source/parent artifacts.

The repository deliberately starts with no fabricated learning-policy champion. Model complexity or promotion is justified only by prospective no-hindsight evidence. See `docs/APEX_LEARNING_GOVERNANCE_V2.md` for the complete Slice 11 operating contract.

## User-facing contract

The only user-facing source is `data/generated/apex_answer_context.json`, which exposes `production_result` only when `safe_to_act=true`. The corresponding canonical JSON/Markdown files are generated by the same production run.

There are exactly two allowed final production selectors:

- `adaptive_gw1_launch_with_transfer_option_value`;
- `receding_horizon_current_team_maximum_ev`.

No static exact-horizon, Elite, CVaR or diagnostic selector may be actionable.

## Readiness gates

A final recommendation requires all of the following on the same sealed surface:

- healthy required sources;
- 100% official hard-fact player coverage;
- 100% required FPL Core player-ID coverage;
- 100% canonical player/Gameweek projection coverage;
- 100% required AIrsenal player/Gameweek xP coverage;
- valid set-piece provenance semantics;
- matched decision-bundle and snapshot hashes;
- optimal diagnostics and solver parity;
- a valid final adaptive/receding strategy;
- exact current-Gameweek mechanics;
- final selected-player evidence identities matching the actual 15;
- final answer context with no blockers.

If any required gate fails, Apex publishes no team.

## Architectural rule

Forecasts, facts and preferences must remain separate. New projection experts cannot be blended through undocumented weights. New selection preferences cannot masquerade as xP. Player-specific hand tuning is prohibited.

After PR #64, architecture is frozen for normal FPL operation. Routine work is source refresh, current-season learning and deadline re-solving. Architecture/model changes reopen only for a demonstrated defect or a bounded challenger that passes the required predictive and decision-level evidence gates.
