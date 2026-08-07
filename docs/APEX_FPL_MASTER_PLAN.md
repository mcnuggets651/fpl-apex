# APEX FPL — Master Build Plan

## Mission
Build a persistent Fantasy Premier League decision engine that maximises expected FPL points using live official data, multiple independent projection signals, exact legal optimisation, uncertainty modelling and current availability/news evidence.

## Non-negotiable principles
- Official FPL is the source of truth for active players, IDs, clubs, positions, prices, status, fixtures and deadlines.
- No single model is blindly trusted. AIrsenal, FPL Core Insights, the Apex model and optional market priors are independent evidence.
- Expected minutes are a first-class model: starts, substitutions, preseason, injuries, manager evidence, tactical role, competition, congestion, transfer risk and line-up evidence all matter.
- Risk-adjusted expected value matters more than headline xP.
- Every important recommendation must include projected value, confidence, key drivers, main risks and the next-best alternative.
- A mathematical output is not a final Apex recommendation unless the safety gate is satisfied.

## Target architecture
1. Data ingestion: official FPL, FPL Core, genuine AIrsenal projections, optional market data, verified context and news.
2. Validation: official-ID matching, club/position/price integrity, freshness and missing-source checks.
3. Features: expected minutes, xG/xA/xGI, clean-sheet probability, defensive contributions, set pieces, penalties, BPS prior, fixture strength, tactical role and risk.
4. Meta-model: row-level expert blending, missing-expert reweighting, uncertainty and risk-adjusted xP.
5. Optimisation: 15-man squad, XI, captain, bench, Haaland/no-Haaland scenarios, transfers, hits and chip strategy.
6. Output: reproducible CSV/JSON/Markdown with source health, blockers, warnings and `safe_to_act`.

## Production acceptance test
Before Apex is called operational it must:
- load and validate the current official FPL pool;
- ingest current FPL Core data;
- ingest genuine AIrsenal GW projections in strict mode;
- produce expected minutes and 1/3/5/8-GW values;
- build a legal 15-player squad and XI/bench/captain;
- compare Haaland and no-Haaland structures;
- expose uncertainty/risk and source provenance;
- fail safely on stale/missing critical sources;
- run deterministically in CI and support scheduled refreshes.

## Milestones
- M0 GitHub read/write and Actions access.
- M1 repository foundation and tests.
- M2 official FPL source of truth and live snapshot.
- M3 AIrsenal/FPL Core/optimisation adapters and pinned upstreams.
- M4 expected minutes, tactical context, injuries/news and set pieces.
- M5 ensemble projections, uncertainty and safety gate.
- M6 legal squad optimiser and Haaland/no-Haaland scenarios.
- M7 personal transfer engine and hits/roll logic.
- M8 chip planning.
- M9 scheduled automation and report persistence.
- M10 walk-forward backtesting/calibration and dynamic source weights.

## Deferred Oracle deployment
Oracle remains optional infrastructure. The core engine should first pass local/GitHub Actions tests and produce `safe_to_act=true`; only then deploy the same container to Oracle for persistent scheduling/API/database workloads.
