# Apex FPL — Architecture

## System flow

```text
Official FPL API
      |
      v
Canonical player/fixture universe
      |
      +--> FPL Core Insights
      +--> pinned AIrsenal
      +--> historical data
      +--> preseason observations
      +--> tactical-role inference
      +--> news / manager / transfer evidence
      +--> Elo / fixture-strength model
      |
      v
Minutes model + player-rate model + team/fixture environment
      |
      v
Apex xP decomposition
(minutes, attack, CS, saves, DEFCON, set pieces, penalties, bonus/BPS)
      |
      v
Projection ensemble
(mean xP, disagreement, confidence, variance, floor/ceiling)
      |
      v
Sealed decision bundle
(content hashes, code/config, evidence, projections, team state)
      |
      v
Maximum-EV legal optimiser  <-------------------+
      |                                          |
      +--> correlated CVaR / scenarios           |
      +--> exact force-ban regret                 |
      +--> captain stability                      |
      +--> independent solver parity              |
      +--> Haaland/no-Haaland counterfactuals     |
      |                                          |
      +--> Elite epsilon frontier ----------------+
                    |
                    v
Canonical strategy
(rolling-horizon maximum-EV only)
                    |
                    v
Exact XI / captain / vice / bench mechanics on raw xP
                    |
                    v
ONE USER-FACING OUTPUT
apex_recommendation_latest.json
                    |
                    v
Personal transfer/chip action + no-hindsight archive
```

## Layer responsibilities
### Canonical universe
Prevents stale names, wrong clubs, wrong positions and invalid prices from contaminating downstream models.

### Evidence ingestion
External repositories/datasets supply complementary evidence. Each source has a defined purpose and must be validated before use.

### Minutes model
Expected minutes is a first-class probabilistic layer. It combines prior/current playing time, preseason participation, availability and news/manual evidence into expected minutes plus start/appearance/60+/80+ probabilities and confidence. It must remain separately calibratable because minutes error multiplies every downstream point component.

### Player-rate model
Uses direct player attacking/defensive rates, role and set-piece evidence rather than assigning a fixed share of team xG. The next upgrade is explicit sample-size shrinkage/partial pooling toward position/role priors so small-sample players do not receive false precision.

### Team / fixture environment
Translates opponent/home/team-strength context into attack and clean-sheet conditions. Future Dixon-Coles/Poisson should enter as an independent expert/challenger, not as sole truth. Elo, xG-based, Poisson and market experts must not be naively averaged; any production combination needs an explicit historically validated rule or stacking procedure.

### Projection layer
Produces transparent per-player/per-GW expected-point components. This is the modelling layer; it is distinct from squad selection.

### Ensemble
Combines experts into the canonical `xp` surface and records disagreement/uncertainty rather than hiding it.

### Sealed decision bundle
Ingestion and projection run once. The resulting player universe, projection
matrix, evidence lineage, source timestamps, settings, upstream pins and team
state are content-addressed by one `bundle_id`. Every optimiser and diagnostic
consumes that bundle; diagnostic layers may not fetch or project independently.
See `docs/DECISION_BUNDLE.md`.

### Maximum-EV optimiser
This is the primary selection baseline. It maximises canonical ensemble xP under budget, club, squad and formation constraints over the selected planning horizon.

### Elite diagnostic frontier
Elite is not a separate forecast or team. It evaluates near-optimal solutions satisfying explicit raw-xP floors at 0%, 0.25%, 0.5% and 1.0%, but cannot change the production selection.

### Canonical selector
There is one deterministic publication rule: the unrestricted rolling-horizon maximum-EV strategy owns the final 15, XI and captain. Elite convergence and other robustness outputs explain sensitivity; no human or diagnostic engine chooses a competing production team.

### Robustness
CVaR, correlated stochastic scenarios, exact regret and solver parity quantify fragility. They are checks, not undocumented substitutions for expected value. Scenario generation must preserve joint football outcomes rather than independently perturb each player.

### Exact deadline mechanics
For the selected 15, XI/captain/vice/bench order are resolved on raw xP with explicit no-show fallback and legal autosub mechanics.

### Ownership / rank strategy
Ownership is not part of the canonical maximum-points objective. Effective ownership may be used only in a separately named rank-management mode where the objective explicitly changes.

### Personal decision layer
Synchronises entry `63984`, bank, transfers, chips and selling prices when public data permits. Uses receding-horizon planning.

### Learning
Archives pre-deadline forecasts and later official outcomes. Model promotion requires repeated out-of-sample evidence.

## User-facing contract
The only user-facing team file is `data/generated/apex_recommendation_latest.json`. Internal `pinnacle_latest.*`, `elite_latest.*`, CVaR and solver outputs are diagnostic artifacts only.

## Readiness gates
The unified recommendation requires:
- `safe_to_act=true`;
- `full_apex_ready=true`;
- `pinnacle_ready=true`;
- matched sealed decision-bundle identity between internal selection diagnostics;
- an optimal selected solution;
- exact GW mechanics present.

If any required gate fails, Apex publishes no team and reports blockers.

## Architectural rule
Forecasts and preferences must remain separate. New selection preferences cannot modify or masquerade as xP. New projection experts cannot be blended through undocumented weights. Every promotion needs explicit benchmark evidence and Project Brain documentation. There must never be more than one user-facing Apex team-selection contract.
