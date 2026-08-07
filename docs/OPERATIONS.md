# Operations

## Recommended operating mode now: GitHub Actions

For the current project, GitHub Actions is the lowest-maintenance runner. The included workflow tests the repository and runs a live refresh every six hours. Live outputs are uploaded as an artifact for 30 days.

No server is required for this mode.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
apex-fpl run --scenario both --horizon 6
```

## Oracle/Linux VM

```bash
git clone <repo-url>
cd apex-fpls
cp .env.example .env
docker compose build
docker compose run --rm apex run --scenario both --horizon 6
```

Example cron in UTC:

```cron
17 */6 * * * cd /opt/apex-fpls && docker compose run --rm apex run --scenario both --horizon 6 >> /var/log/apex-fpl.log 2>&1
```

Increase the cadence around deadlines if required, while respecting upstream rate limits.

## Secrets

No private secret is required for:
- official FPL public bootstrap/fixtures;
- FPL Core public data;
- initial GW1 optimisation.

Optional integrations may require:
- `ODDS_API_KEY` / `ODDS_API_URL`;
- an AIrsenal local export path;
- private or authenticated news feeds if you add any.

Never commit `.env` or credentials. `.gitignore` excludes them.

## Current team state

For transfer planning, use `data/manual/current_squad.csv` and `data/manual/team_state.yaml`. These are local/manual state and should normally remain outside version control if they identify your team choices.

## Reliability rules

1. Official FPL failure stops a live run.
2. Auxiliary-source failure degrades gracefully and is visible in `sources.csv`.
3. Official identity wins source conflicts.
4. Blank Gameweeks produce zero fixture xP.
5. Double Gameweeks are projected fixture-by-fixture.
6. No optional expert is silently imputed.
7. Reports include the generated timestamp and data-quality warnings.
8. CI must pass before deployment.

## Recovery

If a source breaks after an upstream schema change:
- inspect `reports/sources.csv`;
- leave official FPL canonical;
- disable or update the failing adapter;
- rerun tests;
- force refresh with `apex-fpl refresh`.

Do not “fix” a source mismatch by manually changing official player club/position values in the model.
