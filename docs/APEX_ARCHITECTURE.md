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
Pinnacle EV          Elite 10.0
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

### Projection layer
Produces transparent per-player/per-GW expected-point components. This is the modelling layer; it is distinct from squad selection.

### Ensemble
Combines experts into the canonical `xp` surface and records disagreement/uncertainty rather than hiding it.

### Pinnacle
MILP selection on ensemble-mean xP. Initial squad is fixed across the selected horizon while XI/captain can vary by GW as appropriate to the mode.

### Elite
Additional decision utility over the same projection surface. Its job is to favour repeatable attacking ceiling, minutes and captaincy without allowing price efficiency to dominate.

### Robustness
CVaR, stochastic scenarios and exact regret quantify fragility. They are checks, not undocumented substitutions for expected value.

### Personal decision layer
Synchronises entry `63984`, bank, transfers, chips and selling prices when public data permits. Uses receding-horizon planning.

### Learning
Archives pre-deadline forecasts and later official outcomes. Model promotion requires repeated out-of-sample evidence.

## Readiness gates
An Apex Pinnacle recommendation requires `safe_to_act`, `full_apex_ready` and `pinnacle_ready` to be true. Elite additionally requires a valid Elite run on the same current source surface. A stale or red gate must be surfaced explicitly.

## Architectural rule
Do not couple a new decision philosophy directly into the xP forecast. New selection utilities should sit above the canonical projection surface and report their raw-xP opportunity cost.
