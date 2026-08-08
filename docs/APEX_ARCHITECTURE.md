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
      +------------------+
      |                  |
      v                  v
Pinnacle EV          Elite secondary utility
      |                  |
      +---------+--------+
                v
Scenario / robustness layer
(CVaR, force-ban regret, Haaland/no-Haaland, captain/vice, autosubs)
                |
                v
Independent solver parity
                |
                v
Personal team / transfer / chip decision
                |
                v
No-hindsight archive + calibration
```

## Layer responsibilities
### Canonical universe
Prevents stale names, wrong clubs, wrong positions and invalid prices from contaminating downstream models.

### Evidence ingestion
External repositories/datasets supply complementary evidence. Each source has a defined purpose and must be validated before use.

### Minutes model
Expected minutes is a first-class probabilistic layer. It combines prior/current playing time, preseason participation, availability and news/manual evidence into expected minutes plus start/appearance/60+/80+ probabilities and confidence. It must remain separate enough to calibrate independently because minutes error multiplies every downstream point component.

### Player-rate model
Uses direct player attacking/defensive rates, role and set-piece evidence rather than assigning a fixed share of team xG. The next upgrade is explicit sample-size shrinkage/partial pooling toward position/role priors so small-sample players do not receive false precision.

### Team / fixture environment
Translates opponent/home/team-strength context into attack and clean-sheet conditions. Future Dixon-Coles/Poisson should enter as an independent expert/challenger, not as sole truth. Elo, xG-based, Poisson and market experts must not be naively averaged; any production combination needs an explicit historically validated rule or stacking procedure.

### Projection layer
Produces transparent per-player/per-GW expected-point components. This is the modelling layer; it is distinct from squad selection.

### Ensemble
Combines experts into the canonical `xp` surface and records disagreement/uncertainty rather than hiding it.

### Pinnacle
MILP selection on ensemble-mean xP. Initial squad is fixed across the selected horizon while XI/captain can vary by GW as appropriate to the mode.

### Elite
A lexicographic secondary selector, not a forecast. Maximum raw xP is solved first; Elite utility may choose only among near-optimal solutions satisfying an explicit raw-xP floor. The default 0.5% epsilon is provisional and every live run emits a 0/0.25/0.5/1.0% sensitivity frontier. If the frontier is unstable, maximum-EV remains canonical.

### Robustness
CVaR, correlated stochastic scenarios and exact regret quantify fragility. They are checks, not undocumented substitutions for expected value. Scenario generation must preserve joint football outcomes rather than independently perturb each player.

### Ownership / rank strategy
Ownership is not part of the canonical maximum-points objective. Effective ownership may be used only in a separately named rank-management mode where the objective explicitly changes.

### Personal decision layer
Synchronises entry `63984`, bank, transfers, chips and selling prices when public data permits. Uses receding-horizon planning.

### Learning
Archives pre-deadline forecasts and later official outcomes. Model promotion requires repeated out-of-sample evidence.

## Readiness gates
An Apex Pinnacle recommendation requires `safe_to_act`, `full_apex_ready` and `pinnacle_ready` to be true. Elite additionally requires a valid Elite run on the same current source surface and inspection of its raw-xP regret/sensitivity evidence before it can supersede maximum-EV. A stale or red gate must be surfaced explicitly.

## Architectural rule
Forecasts and preferences must remain separate. New selection preferences cannot modify or masquerade as xP. New projection experts cannot be blended through undocumented weights. Every promotion needs explicit benchmark evidence and Project Brain documentation.
