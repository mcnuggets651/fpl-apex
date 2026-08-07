# Apex FPL

**Apex FPL** is a reproducible Fantasy Premier League intelligence and optimisation engine for the 2026/27 season. It is designed to answer one practical question as well as possible: **which legal FPL decisions maximise expected points given the information available now?**

The engine combines live official FPL data with statistical enrichment, preseason evidence, expected minutes, fixture strength, the 2026/27 defensive-contribution rules, optional AIrsenal projections, optional market priors, availability/news signals and mathematical optimisation.

## Core rule

**Official FPL is the canonical source for identity.** Player ID, club, FPL position, price, status and fixtures come from the live official FPL API. Auxiliary sources enrich the model but cannot silently override canonical player identity.

## Apex layers

- Official FPL bootstrap and fixtures as source of truth.
- FPL Core Insights enrichment and preseason evidence.
- AIrsenal projection adapter and export bridge.
- Expected-minutes probabilities and availability modelling.
- Tactical-role and set-piece/penalty context.
- xG, xA, xGI, clean-sheet, save, bonus and defensive-contribution modelling.
- Fixture-strength adjustment and multi-Gameweek horizons.
- Quantified projection uncertainty and risk-adjusted expected points.
- Legal 15-player mathematical squad optimiser.
- Unrestricted, Haaland-locked and no-Haaland structures.
- Multi-Gameweek transfer planning, rolled free transfers and hit costs.
- News/manager-comment layer with inspectable audit output.
- Safety gate that distinguishes diagnostic output from a full Apex recommendation.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
apex-fpl run --scenario both --horizon 8
```

For genuine AIrsenal forecasts, export its prediction database using `scripts/export_airsenal.py` and point `AIRSENAL_PROJECTIONS_CSV` to the resulting file. Configure news feeds and any verified manual tactical/availability inputs before treating the full decision gate as green.

## Reliability

Every run records source status and provenance. Missing optional experts are not replaced by invented numbers; the ensemble reweights over evidence that actually exists. The full decision gate remains blocked when required production sources are missing or stale.

See `docs/` for architecture, model, sources, operations, upstream pins and the master build plan.
