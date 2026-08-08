# Apex FPL — Master Context

**Canonical project brain. Read this before making any Apex recommendation or architectural change.**

## Mission
Build the strongest auditable Fantasy Premier League decision engine possible: maximise expected FPL points and elite scoring ceiling while explicitly measuring uncertainty, minutes risk, downside and model disagreement.

## Repository
- Production repository: `mcnuggets651/fpl-apex`
- Production branch: `main`
- Personal FPL entry: `63984`
- Season focus: 2026/27

## Non-negotiable principles
1. Official FPL is canonical for identity, club, position, price, status and fixtures.
2. Never select a squad from memory or generic FPL opinion when current generated outputs exist.
3. Never trust one model. AIrsenal, Apex projections, FPL Core evidence and independent solver checks are inputs to an ensemble/decision process.
4. Raw expected points remain the canonical forecast. Decision utilities may re-rank evidence but must report any EV regret.
5. Do not optimise points-per-million alone. Premium captaincy, attacking ceiling and repeatable point routes matter.
6. Minutes/start probability is a first-class variable.
7. News/web evidence is a verification/availability layer, not the primary selection engine.
8. Every recommendation must be reproducible, explainable and traceable to a current run.
9. A red data/readiness gate blocks an Apex-labelled recommendation.
10. Football randomness cannot be eliminated; confidence must never be presented as certainty.

## Current engines
### Pinnacle
Primary maximum-EV production engine. It maximises ensemble-mean xP, then separately measures CVaR downside, selection regret, captain/vice fallback, autosubs and independent-solver parity.

### Elite 10.0
Merged additional decision lens designed to correct excessive value-pick bias. It preserves Pinnacle `xp` and adds an Elite utility with weights:
- 35% attacking returns
- 20% expected minutes/start probability
- 15% captaincy value
- 10% set pieces and penalties
- 10% fixture quality
- 5% bonus and DEFCON
- 5% price efficiency

Elite must always be compared with Pinnacle on raw ensemble xP. It is not permission to select famous players without evidence.

## Current production stack
Official FPL → source validation/normalisation → FPL Core Insights → pinned AIrsenal → historical/preseason/tactical/news/strength layers → Apex xP decomposition → projection ensemble → Pinnacle + Elite → stochastic/CVaR/regret/parity checks → final recommendation.

## Expected decision output
A final recommendation should contain the legal 15-man squad, GW XI, captain, vice, bench order, cost/bank, horizon xP, relevant confidence/risk, key scoring routes, scenario comparison (including Haaland/no-Haaland when material), and exact reasons for any human/Elite override of maximum EV.

## Continuity protocol
Before substantive Apex work read, in order:
1. `docs/CURRENT_STATE.md`
2. this file
3. `docs/APEX_DECISIONS.md`
4. `docs/APEX_OPERATING_MANUAL.md`
5. current generated outputs (`pinnacle_latest.json`, `elite_latest.json` when present)

Then continue from the latest state rather than reconstructing the project from chat history.

## Related canonical documents
- [Current state](CURRENT_STATE.md)
- [Decisions](APEX_DECISIONS.md)
- [Architecture](APEX_ARCHITECTURE.md)
- [Model specification](APEX_MODEL_SPEC.md)
- [Data sources](APEX_DATA_SOURCES.md)
- [Operating manual](APEX_OPERATING_MANUAL.md)
- [Roadmap](APEX_ROADMAP.md)
- [Benchmarks](BENCHMARKS.md)
- [Known issues](KNOWN_ISSUES.md)
- [Charter](APEX_CHARTER.md)
- [Vision](VISION.md)
- [Session log](SESSION_LOG.md)
