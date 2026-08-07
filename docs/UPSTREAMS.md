# Upstream integration policy

Apex is a **meta-engine**, not a copy of one FPL repository. Every upstream is pinned in `upstreams.lock.json`, has one explicit job, and can be replaced without changing the official player identity layer.

## Runtime hierarchy

1. **Official FPL API — canonical truth**: player ID, club, position, price, status, fixtures, deadlines and official set-piece order fields.
2. **FPL Core Insights — statistical enrichment**: xG, xA, xGI, team strength/Elo context, player-match detail, preseason GW0, defensive contributions and non-league workload where published.
3. **AIrsenal — independent forecast expert**: genuine AIrsenal player/Gameweek projections imported by official FPL ID. Apex never substitutes `ep_next` or synthetic values and calls them AIrsenal.
4. **Apex transparent model — independent forecast expert**: expected minutes, underlying rates, fixture strength, defensive contributions, set pieces, bonus prior and quantified risk.
5. **Market prior — optional expert**: only from an explicitly configured lawful endpoint.
6. **News/availability layer**: official status plus verified player context and auditable trusted-feed headlines. News can change expected minutes/risk, never identity.
7. **Optimisation layer**: Apex's SciPy/HiGHS MILP is the production solver. `open-fpl-solver` and `FPL-Optimization-Tools` are pinned references/workers for parity testing, transfer/chip strategy ideas and future cross-solver validation.

## Secondary references

- **OpenFPL-Scout-AI** informs heterogeneous ensemble architecture, but is not trusted as 2026/27 live truth without a validated current-season official-ID export.
- **FPL-MCP** informs live-query/tool design; it is not a projection expert.
- **vaastav/Fantasy-Premier-League** is used only for historical/backtest context. It cannot override current official FPL facts.

## Why we do not vendor everything

Blindly merging upstream code would reduce reliability: different projects can lag a season, use different IDs, stale positions or incompatible dependency stacks. Apex consumes validated outputs/contracts and preserves provenance, gaining the useful signal without making any one upstream a single point of failure.

## Reproducibility

`upstreams.lock.json` records exact commits. `scripts/bootstrap_upstreams.sh` checks out the four primary external workers/references at those commits. Every production report records source health. Missing evidence is reported; it is never fabricated.
