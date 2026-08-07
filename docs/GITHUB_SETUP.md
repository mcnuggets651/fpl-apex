# GitHub production setup

The repository is designed so the heavy model workers run in GitHub Actions and the lightweight Apex engine consumes only validated artifacts. Oracle Cloud is optional.

## One-time checks

1. Open **Settings → Actions → General** in this repository.
2. Ensure GitHub Actions is allowed to run.
3. Under **Workflow permissions**, select **Read and write permissions** so the AIrsenal worker can commit its validated forecast artifact.
4. Leave branch protection compatible with `github-actions[bot]` writing `data/generated/airsenal.csv`, or use the worker through a pull request if you later enable strict protected-branch rules.

No FPL password is required for the pre-season forecast worker. The upstream AIrsenal CLI requires a positive team ID for database setup/update, so the worker uses public team ID `1` only to satisfy that upstream interface. Before GW1 its transaction updater is skipped; player forecasts are produced from the model/database, not from that squad.

## First production bootstrap

Run these workflows manually in this order from the **Actions** tab.

### 1. AIrsenal forecast worker

Select **AIrsenal forecast worker → Run workflow**.

The first run can be much slower because it builds AIrsenal's historical database. It then:
- checks out the exact pinned AIrsenal commit;
- builds/updates the model database;
- applies the guarded historical-position workaround for upstream issue #827;
- forecasts the live next eight Gameweeks;
- exports `player.fpl_api_id`, never AIrsenal's internal player key;
- validates official-ID coverage, horizon, timestamp, prediction tag and pinned version;
- runs Apex against the generated forecast;
- commits `data/generated/airsenal.csv` only if the validation passes.

If the workflow fails, **do not create a synthetic replacement file**. The correct state is a red Apex safety gate until the genuine worker succeeds.

### 2. Apex FPL

After the validated AIrsenal file appears in `data/generated/airsenal.csv`, run **Apex FPL → Run workflow**.

A production-green run requires both:
- `safe_to_act=true`
- `full_apex_ready=true`

The workflow intentionally fails when those flags are false, but still uploads the diagnostic report so the blocker is visible.

### 3. Independent solver parity

Run **Independent solver parity → Run workflow**.

This passes the exact same official-ID, risk-adjusted Apex projection table to the pinned `open-fpl-solver` worker and records squad/XI/captain agreement. It is a robustness test, not a replacement authority.

## Scheduled cadence

After bootstrap:
- **AIrsenal forecast worker:** daily at 04:23 UTC.
- **Independent solver parity:** daily at 05:47 UTC.
- **Apex FPL:** every six hours at minute 17.

Around an FPL deadline, manually run AIrsenal then Apex again after important press conferences or late availability news if you want the freshest possible report.

## Optional repository secrets

Open **Settings → Secrets and variables → Actions**.

Optional:
- `ODDS_API_KEY`
- `ODDS_API_URL`
- `APEX_NEWS_FEEDS` — comma-separated extra RSS/Atom URLs

A baseline official/trusted football news configuration is already in `config/news_sources.yaml`, so an extra news secret is not required for the default pipeline.

Never add FPL login passwords or GitHub tokens to tracked files.

## What to inspect after a run

Download the workflow artifact or inspect generated reports locally. The most important files are:
- `reports/latest.json` — machine-readable safety/result contract;
- `reports/latest.md` — human-readable decision report;
- `reports/sources.csv` — source readiness and versions;
- `reports/integrity.csv` — external identity conflicts, with official FPL retained;
- `reports/news_audit.csv` — injury/manager/transfer headline matches;
- `reports/projections.csv` — per-player/per-GW expert projections and uncertainty;
- `reports/solver_parity.json` — independent optimiser agreement when that workflow runs;
- `data/snapshots/latest.json` — official input hashes/provenance.

## Green-light checklist

A final Apex recommendation should only be labelled production-ready when all of these are true:
- current official FPL snapshot loaded;
- no canonical player identity is sourced from an auxiliary repo;
- current pinned FPL Core dataset loaded;
- genuine pinned AIrsenal forecast validated across the requested horizon;
- news/availability layer configured and current;
- expected-minutes and uncertainty fields populated;
- legal 15-player optimiser returns optimal scenarios;
- Haaland and no-Haaland structures both solve when requested;
- `safe_to_act=true`;
- `full_apex_ready=true`;
- tests pass.

Independent solver parity strengthens confidence but is deliberately a cross-check rather than a hard requirement: different legal objectives can sometimes produce different but near-equivalent squads.
