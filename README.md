# Apex FPL

**Apex FPL** is a reproducible 2026/27 Fantasy Premier League intelligence and optimisation engine. Its job is to answer one question as rigorously as possible:

> Given the live FPL player pool, fixtures, projected returns, expected minutes, tactical/availability risk, current news and future flexibility, which legal decision maximises expected FPL points?

Apex deliberately separates a **mathematical result** from a **full recommendation safe to act on**. If a required production source is missing, stale or inconsistent, the engine can still produce a diagnostic squad but writes `safe_to_act=false` rather than pretending confidence.

## Non-negotiable source-of-truth rule

**Official FPL is canonical for player identity.** Official FPL controls:
- player ID;
- club;
- FPL position;
- price;
- availability/status fields;
- fixtures and Gameweeks.

FPL Core, AIrsenal, news, tactical evidence and external solvers may enrich or challenge a projection, but they cannot silently move a player to a different club/position or invent a new price. Conflicts are logged in `reports/integrity.csv`; official FPL wins.

## Apex stack

| Layer | Production role |
|---|---|
| Official FPL API | Live canonical player/team/fixture truth |
| FPL Core Insights | xG/xA/xGI, player/match stats, preseason GW0, team-strength and defensive-contribution enrichment |
| AIrsenal | Genuine independent multi-GW expected-points expert |
| Apex model | Expected minutes, fixture-adjusted xP, tactical/set-piece/bonus/DC context and uncertainty |
| Trusted news / verified context | Injury, transfer, manager and likely-minutes evidence |
| Apex SciPy/HiGHS MILP | Primary legal squad / XI / captain / transfer optimiser |
| Pinned open-fpl-solver | Independent optimisation cross-check on the same official-ID Apex xP |
| FPL Optimization Tools | Pinned formulation/HiGHS reference |
| OpenFPL Scout AI | Ensemble-architecture reference only unless a season-current export is revalidated |
| FPL-MCP | Live-query/tooling architecture reference, not a forecast expert |
| Vaastav FPL history | Historical/backtesting context only |

Exact upstream commits and roles live in `upstreams.lock.json` and `docs/UPSTREAMS.md`.

## What the model includes

### Live and historical evidence
- official FPL bootstrap and fixtures;
- official set-piece/penalty order fields where published;
- FPL Core current-season underlying statistics;
- preseason friendly starts/minutes/xG/xA when published;
- defensive-contribution data for the 2026/27 rules;
- optional market prior;
- trusted RSS/Atom football news plus verified manual overrides;
- immutable official-FPL snapshots and source provenance.

### Expected minutes
Apex models:
- start probability;
- appearance probability;
- expected minutes;
- probability of 60+ minutes;
- probability of 80+ minutes;
- minutes confidence.

Inputs include established usage, preseason usage, official FPL availability, verified role evidence, injuries and conservative news signals. Expected minutes are kept separate from xP so rotation/availability can be audited and calibrated independently.

### Expected points
Per fixture, the transparent Apex model includes:
- appearance points;
- xG/xA attacking value;
- home/away and opponent-strength adjustment;
- clean-sheet probability;
- defensive-contribution value;
- goalkeeper saves where supported;
- capped bonus/BPS prior;
- set-piece and penalty role;
- tactical-role multiplier;
- model uncertainty.

Blank Gameweeks are zeroed explicitly. Double Gameweeks are calculated fixture-by-fixture and summed.

### Ensemble and uncertainty
The row-level ensemble can combine:
- official FPL immediate `ep_next`;
- Apex transparent xP;
- genuine AIrsenal xP;
- optional market xP.

Missing experts are never fabricated. Weights re-normalise over available evidence for diagnostics, while the production safety gate separately decides whether the result is complete enough to act on.

Outputs include:
- 1/3/5/8-GW xP;
- projection standard deviation;
- model disagreement;
- 80% floor/ceiling;
- projection confidence;
- risk-adjusted xP.

## Genuine AIrsenal integration

AIrsenal is an independent expert, not the master database. A critical identity detail is enforced: AIrsenal's `player_prediction.player_id` is an **internal AIrsenal key**. `scripts/export_airsenal.py` joins through the AIrsenal `player` table and exports `player.fpl_api_id` only.

Before an AIrsenal file enters the ensemble, Apex verifies:
- every ID exists in the current official FPL pool;
- every requested Gameweek is present;
- sufficient player coverage exists for each GW;
- `generated_at` is recent;
- `source_version` exactly matches the pinned AIrsenal commit;
- one prediction tag generated the file.

The scheduled `.github/workflows/airsenal.yml` worker:
1. checks out the exact pinned AIrsenal commit;
2. caches its database;
3. updates the live season;
4. produces the next eight GWs of genuine forecasts;
5. exports official FPL IDs;
6. validates them inside Apex;
7. commits `data/generated/airsenal.csv` only after validation.

The first worker run is heavier because the AIrsenal database must be created. If upstream AIrsenal cannot complete a valid 2026/27 run, the safety gate stays red; Apex does not replace it with synthetic values and call them AIrsenal.

## News, transfer and manager evidence

`config/news_sources.yaml` includes a trusted baseline football feed and can be extended with stable official-club RSS/Atom feeds. Headline matching is conservative and auditable:
- injury / ruled-out language reduces expected minutes;
- manager/line-up doubt is classified separately;
- transfer uncertainty can reduce expected minutes;
- return-to-training/start-positive evidence is recorded but cannot push a player above the underlying usage model;
- no headline can alter canonical club/position/price.

Every match is written to `reports/news_audit.csv`. Official FPL availability and verified official-club evidence remain stronger than a general media headline.

## Mathematical optimisation

### Initial squad
The primary SciPy/HiGHS MILP enforces:
- £100.0m budget;
- 15 players;
- 2 GK / 5 DEF / 5 MID / 3 FWD;
- maximum three per club;
- legal starting XI formation;
- captain and vice-captain;
- locked/banned players.

Built-in scenarios:
- unrestricted;
- Haaland locked;
- Haaland banned.

The Haaland/no-Haaland runs are solved independently rather than being a simple one-player swap.

### Multi-GW transfer planning
With an exact current squad, Apex jointly optimises over the horizon:
- squad by Gameweek;
- XI by Gameweek;
- captain/vice;
- transfers in/out;
- bank;
- rolled free transfers up to five;
- four-point hits;
- discounted future xP.

Fixed Wildcard, Bench Boost and Triple Captain weeks are supported. Free Hit remains a separate temporary-squad scenario because its reversion semantics differ from permanent transfers.

## Independent solver parity

`.github/workflows/solver-parity.yml` exports the same official-ID, risk-adjusted Apex xP to the pinned `solioanalytics/open-fpl-solver`, runs its independent optimiser and records:
- 15-player squad overlap;
- XI overlap;
- captain agreement;
- players selected by only one solver.

This does **not** let the external solver override official truth or the safety gate. It is a quantified robustness check against optimisation-formulation mistakes.

The pinned external solver states personal/educational/non-commercial use is permitted and commercial use requires its commercial licence. Apex therefore keeps it isolated and does not vendor its source.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
apex-fpl run --scenario both --horizon 8
```

Main commands:

```bash
apex-fpl run --scenario both --horizon 8
apex-fpl refresh
apex-fpl project --horizon 8
apex-fpl optimise --scenario haaland --horizon 8
apex-fpl optimise --scenario no-haaland --horizon 8
apex-fpl plan-transfers --horizon 8
apex-fpl backtest historical_predictions.csv
```

## Current team input

Before GW1, use the initial-squad optimiser. After the season starts, create `data/manual/current_squad.csv` with exactly 15 official FPL IDs and `data/manual/team_state.yaml` with bank/free-transfer state. Examples live in `data/manual/`.

Apex intentionally does not guess your unrevealed future-deadline transfers from public team history.

## Production safety gate

Every full run emits `safe_to_act` and `full_apex_ready` in `reports/latest.json` and `reports/latest.md`.

The default full gate requires healthy:
- official FPL;
- FPL Core Insights;
- genuine current AIrsenal forecasts;
- configured/current news feed layer;
- legal optimal squad scenarios.

A diagnostic squad can exist while the gate is red. That squad must not be described as the full Apex recommendation.

## GitHub automation

Three workflows are included:

### `apex.yml`
- tests on every push / pull request;
- verifies pinned upstream commits;
- scheduled live run every six hours;
- requires the full production safety gate;
- always uploads diagnostics even if the gate is red.

### `airsenal.yml`
- daily genuine AIrsenal worker;
- exact pinned commit;
- cached model database;
- next-eight-GW forecast;
- official-ID export and strict validation;
- commits the validated forecast for lightweight Apex runs.

### `solver-parity.yml`
- daily independent `open-fpl-solver` cross-check;
- runs from the same Apex projection table;
- uploads quantified solver-agreement evidence.

This makes Oracle optional. Oracle can later host the same container if persistent services, a database/API or richer orchestration are wanted.

## Reports

Each run writes, where applicable:
- `reports/latest.md`;
- `reports/latest.json`;
- `reports/players.csv`;
- `reports/projections.csv`;
- `reports/integrity.csv`;
- `reports/sources.csv`;
- `reports/news_audit.csv`;
- `reports/solver_parity.json` from the parity workflow.

The official snapshot manifest records input hashes so a recommendation can be reconstructed.

## Repository map

```text
src/apex_fpl/
  data/              official FPL, FPL Core, AIrsenal, news, odds
  models/            minutes, fixtures, DC, xP, ensemble, calibration
  optimisation/      initial squad and multi-GW transfer MILPs
  services/          orchestration, integrity, snapshots, news, team state
  reporting/         JSON/CSV/Markdown outputs
scripts/              upstream/export/parity helpers
config/               model and source configuration
data/generated/       validated lightweight worker outputs
data/manual/          explicit private/manual inputs
.github/workflows/    tests, live pipeline, AIrsenal worker, solver parity
docs/                 architecture, model, sources and operations
tests/                deterministic regression/unit tests
```

## Design philosophy

Apex cannot make football certain. A high Apex rating means the **decision process** is current, validated, mathematically legal, uncertainty-aware and reproducible. It does not mean a player cannot blank, be rotated unexpectedly or get injured after the deadline.

## Licence

Apex itself is MIT. External workers retain their own licences and are not vendored into this repository.
