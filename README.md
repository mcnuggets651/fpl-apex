# Apex FPL — Pinnacle Decision Engine

Apex FPL is a reproducible 2026/27 Fantasy Premier League decision system built to answer:

> Given everything we can defensibly know before the deadline, which legal FPL decision maximises expected points, how robust is it, and what would make us change it?

The production personal entry is **FPL ID 63984**.

## Start here

The complete operating guide is **[`docs/PINNACLE_USER_GUIDE.md`](docs/PINNACLE_USER_GUIDE.md)**.

The single most important rule is that a recommendation is called **Apex Pinnacle** only when `data/generated/pinnacle_latest.json` says all three are true:

```json
{
  "safe_to_act": true,
  "full_apex_ready": true,
  "pinnacle_ready": true
}
```

If the gate is red, the engine reports the blocker instead of serving an old team.

## What Pinnacle uses

- **Official FPL** as canonical source for player ID, club, FPL position, price, status and fixtures.
- **FPL Core Insights** for current underlying stats, preseason, Elo/strength and defensive-contribution context.
- **Genuine pinned AIrsenal** as an independent expected-points expert, mapped only through official FPL IDs.
- **Apex xP decomposition** for expected minutes, xG/xA/xGI, clean sheets, saves, defensive contribution, set pieces, penalties, tactical role and 2026/27 bonus/BPS.
- **Trusted news/manager/transfer evidence** for short-lived availability and role changes without letting headlines overwrite official identity.
- **Projection ensemble** with disagreement, confidence, standard deviation and floors/ceilings.
- **Maximum-EV full-horizon MILP** that keeps the 15-player initial squad fixed but optimises XI and captain separately in every Gameweek.
- **Correlated stochastic scenarios** with club attack/defence, opponent, Gameweek and persistent player-role/minutes uncertainty.
- **CVaR MILP** as a lower-tail robustness cross-check.
- **Exact selection regret** by force/ban re-optimisation.
- **Exact captain/vice fallback and autosub mechanics** for the final deadline recommendation.
- **Independent pinned open-fpl-solver parity** on the same ensemble-mean xP surface.
- **Personal team synchronisation** for entry 63984, including bank, rolled free transfers, chip history and reconstructed selling prices.
- **Receding-horizon weekly transfer strategy**: execute only the next action, then re-solve after new information.
- **No-hindsight learning archive** that stores genuine pre-deadline forecasts and attaches official outcomes only after the Gameweek finishes.

Exact upstream revisions are locked in `upstreams.lock.json`.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,airsenal]'

export FPL_ENTRY_ID=63984
apex-fpl pinnacle --horizon 8
apex-fpl pinnacle-status
```

Equivalent explicit command:

```bash
python scripts/run_pinnacle.py \
  --horizon 8 \
  --stochastic-scenarios 256 \
  --cvar-alpha 0.10 \
  --cvar-weight 0.20 \
  --force
python scripts/assert_pinnacle.py
```

## Use it from ChatGPT

The intended user interface is the conversation, not a separate app. Examples:

```text
Give me the latest Apex Pinnacle team.
Stress-test Haaland vs no Haaland.
What is my best transfer this week?
Should I roll? Show the exact value of rolling.
Is a -4 justified?
Give me the action now and contingent 3-GW path.
Who should I captain and vice-captain?
What is the exact bench order?
Should I wildcard now or wait?
Which current picks are mathematically fragile?
Does CVaR or the independent solver disagree?
How has the model performed so far this season?
```

ChatGPT should read `data/generated/pinnacle_latest.json` first rather than reuse a remembered historical team.

## Personal FPL workflow

Before GW1, FPL does not expose an unpublished draft, so Pinnacle builds the optimal initial squad from scratch.

After each deadline, entry **63984** supplies the latest public 15-player squad, bank, captain/vice, transfer/chip history and rolled free-transfer state. Manager-specific selling prices are reconstructed from the captured pre-GW1 official price universe plus later public purchase prices.

Public FPL picks are deadline snapshots. If a transfer has already been privately made for the next deadline, provide that change as a manual override; the public API cannot see it yet.

## Mathematical decision hierarchy

1. Maximise expected FPL points on ensemble mean `xp`.
2. Check the correlated CVaR solution for downside sensitivity.
3. Re-solve force/ban cases to quantify exact selection regret.
4. Recalculate captain, vice and bench order with exact fallback/autosub expectation.
5. Cross-check the independent solver on the same xP surface.
6. Act only if all required source and Pinnacle gates are green.

Risk is therefore **measured separately**, not silently baked into the primary objective twice.

## Weekly transfer philosophy

Pinnacle does not tell you to blindly follow a static eight-week transfer script. It uses **receding horizon** optimisation:

- solve the full next several Gameweeks;
- compare the best action with the explicit roll counterfactual;
- execute only the current action;
- treat later transfers as contingencies;
- refresh prices, injuries, expected minutes, news and fixtures;
- solve again at the next deadline.

The candidate universe also protects positional options, cheap enablers, price-band leaders, Pareto-efficient assets and one-week fixture punts from naive global top-N pruning.

## Chips

The personal state stores used-chip history and the engine evaluates the current Wildcard, Free Hit, Bench Boost and Triple Captain window under the 2026/27 rules.

Chip value is reported as opportunity evidence. A positive immediate gain is not by itself an instruction to spend a scarce chip because future Blank/Double Gameweeks may be more valuable.

## Learning without hindsight

The Pinnacle workflow maintains `data/history/deadlines/`.

Within 30 hours of each deadline it refreshes that Gameweek's green pre-deadline forecast. Once Official FPL marks the event finished, official points are attached. `data/generated/calibration_report.json` then reports expert error/ranking performance, candidate ensemble calibration and a genuine latest-GW holdout check when enough history exists.

Weights are **not automatically changed after one good sample**. Promotion remains conservative until repeated out-of-sample evidence establishes a stable improvement.

## GitHub automation

The key workflows are:

- **Apex Pinnacle** — full tests, upstream validation, genuine AIrsenal refresh, live production gate, maximum-EV/CVaR/regret/mechanics run, strict Pinnacle gate, deadline learning archive and repository-readable snapshot. Scheduled every six hours and manually dispatchable.
- **Publish independent solver parity** — runs the pinned external solver on the same Pinnacle ensemble-mean xP and embeds the comparison back into the snapshot.
- **Apex / AIrsenal / FPL Core refresh workflows** — maintain the validated source and diagnostic layers underneath Pinnacle.

A dedicated final pre-GW1 run is scheduled for the morning of **21 August 2026**.

## Main outputs

- `data/generated/pinnacle_latest.json` — machine-readable final decision.
- `data/generated/pinnacle_latest.md` — human-readable final decision.
- `data/generated/apex_latest.json` — validated base production state.
- `data/generated/solver_parity.json` — independent same-surface optimisation check.
- `data/generated/airsenal.csv` — genuine AIrsenal projections.
- `data/generated/calibration_report.json` — historical learning status.
- `data/history/deadlines/gwXX_forecast.csv` — no-hindsight forecast/outcome archive.
- `reports/pinnacle_selection_regret.csv` — exact decision sensitivity.
- `reports/pinnacle_scenario_player_summary.csv` — stochastic player summaries.
- `reports/team_state.json` — current public/manual personal team state.

## Known-data boundary

Apex Pinnacle can improve the quality of the decision; it cannot remove football randomness. The initial covariance coefficients are transparent priors because 2026/27 outcomes do not exist before the season. They are explicitly flagged and can be validated as the no-hindsight archive grows.

The standard is not certainty. The standard is **the strongest auditable decision that the available data supports**.

## Licence

Apex itself is MIT. External workers keep their own licences and are not vendored into this repository.
