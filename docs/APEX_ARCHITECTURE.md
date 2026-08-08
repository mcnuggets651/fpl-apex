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
      +--> historical data / xG
      +--> preseason observations
      +--> tactical-role inference
      +--> news / manager / transfer evidence
      +--> Elo / fixture-strength model
      +--> future Dixon-Coles/Poisson challenger
      |
      v
Team / fixture scoring environment
      |
      v
Apex player xP decomposition
(minutes, attack, CS, saves, DEFCON, set pieces, penalties, bonus/BPS)
      |
      v
Projection ensemble
(mean xP, disagreement, confidence, variance, floor/ceiling)
      |
      v
Pinnacle maximum-EV solve
      |
      +--> unrestricted maximum xP
      +--> Haaland maximum xP
      +--> no-Haaland maximum xP
      |
      v
Elite secondary solve inside near-optimal xP band
(35/20/15/10/10/5/5; default epsilon 0.5%)
      |
      v
Raw-xP XI / captain / vice re-optimisation
      |
      v
Scenario / robustness layer
(CVaR, correlated uncertainty, force-ban regret, autosubs, captain persistence)
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

### Team / fixture scoring environment
Produces expected scoring and clean-sheet context for each fixture. Multiple experts may contribute. Dixon-Coles/Poisson is a valid independent challenger because it models goal counts coherently, but it must be benchmarked against the existing Elo/history/xG ensemble rather than replacing it by assumption.

### Projection layer
Produces transparent per-player/per-GW expected-point components. Player attacking rates are player-specific and minutes/role aware; team scoring expectation constrains the environment but does not mechanically assign every player's return via one historical team-share ratio.

### Ensemble
Combines experts into the canonical `xp` surface and records disagreement/uncertainty rather than hiding it.

### Pinnacle
MILP selection on ensemble-mean xP. This is the primary squad-selection objective. Initial squad is fixed across the selected horizon while XI/captain can vary by GW as appropriate to the mode.

### Elite
Secondary preference layer only. For each scenario, Apex first establishes the maximum-xP objective. Elite may then choose among solutions inside a strict near-optimal raw-xP band. It cannot create or modify expected points. The selected squad is re-solved on raw xP for XI, captain and vice.

### Robustness
CVaR, stochastic scenarios and exact regret quantify fragility. Scenarios preserve correlated team/player/minutes effects; they are not independent random noise around each player's mean.

### Ownership / rank strategy
Ownership is not part of maximum-points selection. If an explicit rank-protection or rank-chasing mode is requested, ownership/EO can be introduced as a documented secondary game-theoretic layer or tiebreak.

### Personal decision layer
Synchronises entry `63984`, bank, transfers, chips and selling prices when public data permits. Uses receding-horizon planning.

### Learning
Archives pre-deadline forecasts and later official outcomes. Model promotion requires repeated out-of-sample evidence.

## Readiness gates
An Apex Pinnacle recommendation requires `safe_to_act`, `full_apex_ready` and `pinnacle_ready` to be true. Elite additionally requires a valid same-snapshot secondary solve whose raw-EV regret respects the configured epsilon band. A stale or red gate must be surfaced explicitly.

## Architectural rule
Forecasts and preferences are separate. Expected points come from the projection stack; selection utilities sit above it. Any secondary decision layer must expose and constrain its raw-xP opportunity cost.
