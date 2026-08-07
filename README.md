# Apex FPL

**Apex FPL** is a reproducible Fantasy Premier League intelligence and optimisation engine for the 2026/27 season. It is designed to answer one practical question as well as possible: **which legal FPL decisions maximise expected points given the information available now?**

The engine combines live official FPL data with statistical enrichment, preseason evidence, expected minutes, fixture strength, the 2026/27 defensive-contribution rules, optional AIrsenal projections, optional market priors, availability/news signals and mathematical optimisation.

## The non-negotiable rule

**Official FPL is the canonical source for identity.** Player ID, club, FPL position, price, status and fixtures come from the live official FPL API. Auxiliary sources may enrich a player, but they cannot silently move him to a different club or position. Conflicts are written to `reports/integrity.csv` and the official value wins.

That rule exists specifically to prevent stale-transfer errors from contaminating recommendations.

## What is implemented

### Live data and integrity
- Official FPL `bootstrap-static` and fixtures.
- FPL Core Insights 2026/27 `playerstats.csv` enrichment.
- FPL Core preseason/friendly player-match data under Gameweek 0.
- Source-health and provenance output on every run.
- Canonical identity reconciliation with conflict reporting.
- Disk caching and explicit force-refresh mode.

### Player modelling
- Expected-minutes model using established minutes, preseason starts/minutes, official availability, manual verified overrides and optional news signals.
- xG/90 and xA/90 attacking projection with conservative preseason blending.
- Fixture attack/defence multipliers.
- Explicit Blank Gameweek zeroing and Double Gameweek multi-fixture summation.
- 2026/27 defensive-contribution model: defender CBIT and midfielder/forward CBIRT thresholds.
- Goalkeeper save-point contribution when a valid saves/90 signal exists.
- Set-piece and penalty-order context.
- Capped bonus-points prior rather than pretending future BPS can be known exactly.
- Per-player uncertainty and configurable risk adjustment.

### Projection ensemble
A row-by-row expert blend can use:
- Official FPL immediate `ep_next`.
- Apex transparent expected-points model.
- Optional AIrsenal export.
- Optional market expected-points prior.

Missing experts are **not** replaced with made-up numbers. The weights automatically re-normalise over the evidence that is actually available.

### Initial squad optimisation
A SciPy/HiGHS mixed-integer optimiser selects:
- legal 15-player squad;
- legal starting XI;
- captain;
- bench;
- maximum three players per club;
- £100.0m budget;
- position constraints;
- locked/banned players.

Built-in scenario runs:
- unrestricted optimum;
- Haaland locked;
- Haaland banned.

### Multi-Gameweek transfer optimisation
When an exact current squad is supplied, Apex jointly optimises over the configured horizon:
- squad by Gameweek;
- XI by Gameweek;
- captain by Gameweek;
- transfers in/out;
- bank;
- rolled free transfers from 1 to 5;
- four-point transfer hits;
- discounted future xP.

The rolled-free-transfer state is modelled explicitly rather than approximated. Current prices are held static during the horizon so the engine does not invent future price movements.

The optimisation code also supports fixed Wildcard, Bench Boost and Triple Captain weeks. Free Hit is kept conceptually separate from permanent squad planning because its one-week squad-reversion rule is different.

### Availability/news layer
- Optional verified manual availability overrides.
- Configurable RSS/Atom feeds.
- Conservative player-name/headline matching for obvious injury/return language.
- Full `news_audit.csv` output so headline-derived adjustments are inspectable.
- News never changes player identity and remains weaker than official availability evidence.

### Reliability and calibration
- Unit tests for identity integrity, expected minutes, ensemble weighting, legal squad optimisation, multi-GW transfer rules, blanks and doubles.
- Historical backtest helper with MAE, RMSE, bias and rank correlation.
- GitHub Actions tests on push/PR.
- Scheduled live pipeline every six hours.
- Docker deployment for Oracle Cloud or any Linux host.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
apex-fpl run --scenario both --horizon 6
```

The first run needs no private FPL credentials when building a GW1 squad.

## Main commands

```bash
# Full live run: refresh -> project -> optimise -> report
apex-fpl run --scenario both --horizon 6

# Force fresh public-source downloads
apex-fpl refresh

# Projection/ranking run
apex-fpl project --horizon 6

# Initial squad scenario
apex-fpl optimise --scenario unrestricted --horizon 6
apex-fpl optimise --scenario haaland --horizon 6
apex-fpl optimise --scenario no-haaland --horizon 6

# Multi-GW transfer plan once an exact current squad is supplied
apex-fpl plan-transfers --horizon 6

# Historical calibration
apex-fpl backtest historical_predictions.csv
```

## Current squad input

Before the season starts, transfers are unlimited and the initial-squad optimiser is the correct mode. After the season starts, create:

`data/manual/current_squad.csv`

```csv
player_id
123
456
...
```

It must contain exactly 15 unique official FPL IDs.

`data/manual/team_state.yaml`

```yaml
bank: 0.5
free_transfers: 2
```

This is intentionally explicit. Public FPL picks do not reveal transfers made for a future deadline before that deadline, so Apex will not pretend an old public team is your current team.

## AIrsenal integration

AIrsenal is treated as an **independent expert**, not as the master database. This makes the system resilient when AIrsenal's season migration or dependencies lag the official FPL launch.

Install the optional dependency when the upstream project supports the live season:

```bash
pip install -e '.[airsenal]'
```

Expose an AIrsenal projection export with `AIRSENAL_PROJECTIONS_CSV`. Apex accepts either:

```text
player_id,gw,xp
```

or a wide table:

```text
player_id,GW1,GW2,GW3
```

If the export is absent, a diagnostic mathematical run can still be generated, but **strict Apex mode sets `safe_to_act=false`**. The ensemble may re-normalise its remaining experts for inspection; Apex does not call that a final Apex recommendation and never labels synthetic/FPL values as AIrsenal.

## FPL Core Insights integration

Apex reads the current `data/2026-2027/` outputs from FPL Core Insights, including the preseason `By Tournament/Friendlies/GW0/playermatchstats.csv` file. It uses those fields for statistical context only; official FPL identity always wins.

## Reports

Each full run writes:
- `reports/latest.md` — readable decision report.
- `reports/latest.json` — machine-readable report.
- `reports/players.csv` — ranked player table.
- `reports/projections.csv` — player/Gameweek expert and ensemble projections.
- `reports/integrity.csv` — source conflicts.
- `reports/sources.csv` — source-health/provenance table.
- `reports/news_audit.csv` — matched headlines and inferred advisory signals.

If a current squad is configured, the report also includes the multi-Gameweek transfer plan.

## GitHub Actions

`.github/workflows/apex.yml`:
- tests every push and pull request;
- runs the live Apex pipeline every six hours;
- can be run manually;
- uploads `reports/` as a workflow artifact.

This means the modelling engine can operate without Oracle Cloud. Oracle remains useful if you want a continuously managed service, custom APIs, a database, or more frequent orchestration.

## Docker / Oracle Cloud

```bash
docker compose build
docker compose run --rm apex run --scenario both --horizon 6
```

See `docs/OPERATIONS.md`.

## Design philosophy

Apex does **not** claim football can be predicted perfectly. A “10/10” Apex recommendation means the decision pipeline is using the intended evidence, rules and constraints cleanly—not that a player cannot blank or get injured after the deadline.

The system therefore prioritises:
1. correct live identity;
2. secured/minutes-weighted opportunity;
3. expected points rather than last-match points;
4. reproducible mathematical constraints;
5. source provenance;
6. calibrated uncertainty;
7. graceful degradation when optional sources are absent.

## Repository map

```text
src/apex_fpl/
  data/             official FPL, FPL Core, AIrsenal, news, odds
  models/           minutes, fixtures, DC, xP, ensemble, backtest
  optimisation/     initial squad and multi-GW transfer MILPs
  services/         orchestration, integrity, enrichment, news, team state
  reporting/        JSON/CSV/Markdown report generation
config/              model and news configuration
data/manual/         explicit private/manual inputs (not committed by default)
docs/                architecture, model, sources and operations
.github/workflows/   test + scheduled live pipeline
tests/               deterministic unit tests
```

## Upstream acknowledgements

Apex uses public outputs, pinned worker contracts and/or design validation from:
- The Alan Turing Institute's **AIrsenal**.
- **FPL Core Insights** by olbauday.
- **open-fpl-solver** and **FPL Optimization Tools** for optimisation/reference parity.
- **OpenFPL-Scout-AI** as a secondary ensemble architecture reference.
- **FPL-MCP** as a live-query/tooling architecture reference.
- **vaastav/Fantasy-Premier-League** for historical/backtest context only.

Exact upstream commits and roles are in `upstreams.lock.json` and `docs/UPSTREAMS.md`.

Apex does not vendor those codebases. Its own optimiser and data-contract layer are independent so each upstream source can evolve without becoming a single point of failure.

## Licence

MIT. See `LICENSE`.
