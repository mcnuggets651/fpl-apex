# Upstream integration policy

Apex does **not** copy several FPL projects into one fragile monolith. Each upstream has a
clear contract and exact pinned commit in `upstreams.lock.json`. Official FPL is always the
identity/price/position/club/fixture authority.

| Upstream | Apex role | Runtime authority |
|---|---|---|
| Alan Turing Institute AIrsenal | Independent multi-GW expected-points worker | Forecast only; never identity |
| FPL Core Insights | xG/xA/xGI, player/match, preseason, team-strength enrichment | Statistical enrichment only |
| Solio `open-fpl-solver` | Independent transfer/chip optimisation reference | Cross-check / future worker |
| `ratisil/FPL-Optimization-Tools` | Optimisation formulation reference | Cross-check / future worker |
| OpenFPL Scout AI | Optional ensemble forecast reference when season-compatible | Optional expert only |
| FPL-MCP | API/query interface patterns | No modelling authority |
| Vaastav Fantasy-Premier-League | Historical/backtesting data | Historical only, not live truth |

## Why this design

An upstream package can lag a new season, change a player's position mapping, or refresh on a
different cadence. Apex therefore reconciles everything through official FPL IDs and fails
safely instead of allowing an auxiliary source to overwrite a current club, position or price.

The core optimiser is implemented locally with SciPy/HiGHS so a recommendation remains
reproducible. External solvers are used as independent formulation references and can be
added as workers without changing the canonical data model.
