# Live validation — 7 August 2026

A clean checkout of `main` was validated end-to-end against live public sources on 7 August 2026.

## Repository checks

The following completed successfully in a clean Python environment:

```bash
pip install -e '.[dev]'
pytest -q
ruff check src tests scripts
```

## Live source / optimiser validation

The production path was then exercised with a genuine pinned AIrsenal worker:

```bash
pip install -e '.[airsenal]'
export AIRSENAL_DB_FILE=/tmp/apex-airsenal.db
airsenal_setup_initial_db
python scripts/run_airsenal_worker.py \
  --db "$AIRSENAL_DB_FILE" \
  --horizon 8 \
  --output data/generated/airsenal.csv

export AIRSENAL_PROJECTIONS_CSV=data/generated/airsenal.csv
apex-fpl run --scenario both --horizon 8 --force
python scripts/assert_full_apex.py reports/latest.json
```

The final command returned:

```text
FULL APEX GATE: READY
```

That means the generated report passed the strict production contract rather than merely returning a mathematically legal squad. The gate requires:

- fresh, validated official FPL snapshot and SHA256 provenance;
- FPL Core statistical enrichment;
- a genuine AIrsenal projection export using official FPL IDs;
- a healthy configured news layer;
- Optimal unrestricted, Haaland and no-Haaland scenarios;
- legal 15-player squads and 11-player XIs;
- captain and vice-captain outputs;
- no unresolved production blocker from the Apex safety layer.

## What this validation does *not* mean

It does not mean football outcomes are certain, nor does it freeze a squad recommendation in Git. Prices, transfers, injuries, tactical roles, expected minutes and news change. Live team outputs therefore remain generated artefacts rather than committed source code.

The scheduled GitHub Actions workflows reproduce the same process and upload the current reports as workflow artefacts.
