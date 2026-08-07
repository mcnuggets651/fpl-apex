# Using Apex Pinnacle directly from ChatGPT

ChatGPT is the intended user interface for the decision engine. GitHub Actions performs the reproducible computation; compact repository snapshots are the durable contract between the workers and ChatGPT. No separate app is required.

## Files ChatGPT should read first

For a current recommendation, inspect in this order:

1. `data/generated/pinnacle_latest.json`
   - deterministic full-horizon unrestricted / Haaland / no-Haaland solutions;
   - covariance-aware CVaR robustness solutions;
   - deterministic-vs-robust overlap;
   - exact force/ban selection regret;
   - scenario downside / median / upside summaries;
   - current personalised team/transfer state when public;
   - source health and official-snapshot provenance.
2. `data/generated/pinnacle_latest.md`
   - human-readable version of the enhanced decision run.
3. `data/generated/apex_latest.json`
   - latest production-green core fallback if the Pinnacle snapshot is not yet published.
4. `data/generated/solver_parity.json`
   - independent Apex-vs-open-fpl-solver mathematical parity evidence.
5. `data/generated/airsenal.csv`
   - genuine pinned AIrsenal player/Gameweek projection evidence.
6. `upstreams.lock.json`
   - exact upstream revisions used by the pipeline.

Never answer a current team question from remembered historical picks when repository decision files are available.

## Decision gate

A current Pinnacle recommendation requires at minimum:

```json
{
  "safe_to_act": true,
  "full_apex_ready": true
}
```

Then inspect the deterministic-vs-CVaR agreement and selection-regret margins. A legally optimal squad with weak source health or near-zero regret margins should not be presented as a high-confidence pick.

If `pinnacle_latest.json` is missing, stale or blocked, use the latest green `apex_latest.json` only as the core fallback and say that the enhanced stress layer is not currently published.

## Personal FPL entry

The 2026/27 pipeline is configured for FPL entry **63984**.

Before GW1 the public FPL API cannot reveal the live unpublished draft, so Pinnacle correctly builds the strongest initial squad from scratch.

After each deadline the engine reads the latest public 15-player squad, bank, captain/vice, transfer/chip history and available free transfers. It then optimises from the next open deadline over the requested horizon.

Public entry state is a deadline snapshot. If a transfer has already been made privately after that deadline, tell ChatGPT the change; the explicit/manual state must override the older public snapshot.

The pipeline captures the pre-GW1 official price universe and combines it with later public purchase prices to reconstruct manager-specific selling values under FPL's half-profit rule.

## Natural interaction

You can use plain language. Examples:

- `Run Pinnacle now. Give me the strongest 15.`
- `Give me the final GW1 team and stress-test every pick.`
- `Compare Haaland vs no Haaland with expected-value gaps.`
- `Do the deterministic and CVaR squads agree?`
- `Which picks are fragile and what is their replacement regret?`
- `What is my best transfer this week?`
- `Roll or transfer? Show the 1-GW, 3-GW and 5-GW maths.`
- `Is a -4 mathematically justified?`
- `Give me the best transfer path for the next 5 Gameweeks.`
- `Should I wildcard now or preserve it?`
- `Who should I captain and vice-captain?`
- `Why is Player X above Player Y?`
- `What new information would make Player Y optimal?`
- `Does the independent solver agree with the decision?`

For player-vs-player analysis, use expected minutes, appearance/start probabilities, xG/xA/xGI, fixture context, tactical role, set-piece shares, defensive/bonus potential, projection disagreement, CVaR/downside and exact regret rather than a single headline xP number.

## GitHub interaction

To force a fresh enhanced run manually:

1. open the repository **Actions** tab;
2. choose **Apex Pinnacle**;
3. choose **Run workflow** on `main`;
4. after the workflow completes, ChatGPT should read `data/generated/pinnacle_latest.json`.

The core command-line equivalents are:

```bash
apex-fpl run --scenario both --horizon 8 --force
apex-fpl sync-team
apex-fpl plan-transfers --horizon 8 --force
python scripts/run_pinnacle.py --horizon 8 --force
```

## Freshness cadence

The repository is designed around:

- FPL Core data-pin refresh every six hours;
- normal personalised Apex publish every six hours;
- Apex Pinnacle full-horizon + 256-scenario CVaR run every six hours;
- genuine AIrsenal refresh inside production runs;
- independent solver parity on its validation cadence;
- a dedicated final pre-GW1 run on 21 August 2026 morning;
- manual reruns close to deadlines after important press conferences, injuries or transfer news.

The goal is not to create the most complicated model possible. It is to create the most **defensible decision** possible: current data, independent forecasts, transparent uncertainty, legal hard optimisation, robustness checks and explicit expected-value trade-offs.
