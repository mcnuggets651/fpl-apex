# Upstream integration policy

Apex does **not** copy several FPL projects into one fragile monolith. Each upstream has a
clear contract and exact pinned commit in `upstreams.lock.json`. Official FPL is always the
identity/price/position/club/fixture authority.

| Upstream | Apex role | Runtime authority |
|---|---|---|
| Alan Turing Institute AIrsenal | Independent multi-GW expected-points worker | Forecast only; never identity |
| FPL Core Insights | xG/xA/xGI, player/match, preseason, team-strength enrichment | Statistical enrichment only |
| Solio `open-fpl-solver` | Independent optimisation worker using the same Apex xP | Daily cross-solver robustness check |
| `ratisil/FPL-Optimization-Tools` | Optimisation formulation / HiGHS reference | Pinned parity reference; no identity authority |
| OpenFPL Scout AI | Ensemble architecture reference when season-compatible | Not used as live 2026/27 truth unless revalidated |
| FPL-MCP | API/query interface patterns | No modelling authority |
| Vaastav Fantasy-Premier-League | Historical/backtesting data | Historical only, not live truth |

## Why this design

An upstream package can lag a new season, change a player's position mapping, or refresh on a
different cadence. Apex therefore reconciles everything through official FPL IDs and fails
safely instead of allowing an auxiliary source to overwrite a current club, position or price.

The production optimiser is implemented locally with SciPy/HiGHS so every recommendation is
reproducible. The pinned Solio solver is also run independently on **the same official-ID Apex
projection table** by `.github/workflows/solver-parity.yml`. Apex then records 15-player squad
overlap, XI overlap and captain agreement. This is useful quantified robustness evidence: a
solver disagreement is investigated rather than silently averaged away.

The Solio project currently states personal/educational/non-commercial use is permitted and
commercial entities require its commercial licence. Apex therefore keeps that worker isolated
and does not vendor its source. If this Apex project ever becomes commercial, disable that
worker until the appropriate external licence is confirmed.

## Genuine AIrsenal boundary

AIrsenal has its own internal player primary key. Apex must **never** treat that key as an FPL
ID. `scripts/export_airsenal.py` joins `player_prediction.player_id` to `player.player_id` and
exports `player.fpl_api_id` only. The adapter then checks:

- every ID exists in the current official FPL pool;
- every requested Gameweek is present;
- minimum player coverage per Gameweek;
- the export timestamp is fresh;
- `source_version` equals the pinned AIrsenal commit; and
- one prediction tag generated the file.

Only after those checks may AIrsenal enter the ensemble.

## Secondary references are not fake experts

OpenFPL-Scout-AI is useful as an ensemble design reference, but its published model material is
not treated as current 2026/27 evidence without a current official-ID export. FPL-MCP is useful
for live query/tool patterns but is not a projection model. Vaastav is valuable for historical
walk-forward testing, but current facts come from official FPL and current FPL Core data.

This distinction is deliberate: "using all repositories" means taking the useful, validated
capability from each one, not giving stale or irrelevant code a vote in the final squad.
