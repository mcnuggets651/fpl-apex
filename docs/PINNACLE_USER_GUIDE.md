# Apex Pinnacle — final operating guide

Apex Pinnacle is the decision layer above the validated Apex FPL data pipeline. The objective is not to produce a fashionable team; it is to make the strongest reproducible FPL decision available from current public/verified evidence while exposing uncertainty instead of hiding it.

The configured personal FPL entry is **63984**.

## What counts as a Pinnacle recommendation

A recommendation is Pinnacle only when `data/generated/pinnacle_latest.json` contains:

```json
{
  "safe_to_act": true,
  "full_apex_ready": true,
  "pinnacle_ready": true
}
```

If any flag is false, the correct output is the blocker — not an old squad.

## Decision stack

1. **Official FPL truth** — player ID, club, FPL position, price, availability and fixtures.
2. **FPL Core enrichment** — underlying statistics, preseason, Elo/strength and defensive-contribution context.
3. **Genuine pinned AIrsenal** — independent multi-Gameweek projection expert, mapped through official FPL IDs.
4. **Field-level data gate** — rejects non-informative official strength, missing fixture/player projection surfaces, malformed forecasts and false zero preseason evidence.
5. **Apex transparent xP** — expected minutes, prior-season playing time, xG/xA/xGI, fixture strength, tactical role, clean sheets, saves, defensive contributions, set pieces, penalties and 2026/27 bonus/BPS.
6. **Understat team-goal challenger** — five complete seasons, canonical teams and promoted-club priors. It remains in shadow mode until the complete promotion gate passes.
7. **Trusted news/availability layer** — injuries, return dates, transfer uncertainty and manager/line-up evidence. It cannot overwrite Official FPL identity.
8. **Ensemble** — combines available projection experts, reports disagreement, standard deviation, floors/ceilings and confidence. Full-Gameweek experts are allocated exactly once across DGW fixture rows so they cannot be silently doubled.
9. **Maximum-EV full-horizon MILP** — fixed initial 15, legal XI and captain optimised separately in every Gameweek. The primary objective uses ensemble mean `xp`; uncertainty is not silently double-counted as a risk penalty.
10. **Correlated scenario model** — shared Gameweek/team attack/team defence/opponent shocks plus persistent player minutes/role uncertainty across the horizon.
11. **CVaR MILP** — a second solution balances mean return with lower-tail robustness. It exposes fragility rather than automatically preferring the safest squad.
12. **Exact selection regret** — selected players are banned and strong alternatives are forced, then the full problem is re-solved on the same maximum-EV surface.
13. **Exact deadline mechanics** — captain/vice no-show fallback and the best outfield bench order are evaluated explicitly. Autosubs enumerate the relevant appearance states subject to legal FPL formation rules.
14. **Decision-frequency audit** — repeated correlated re-solves publish squad, XI, captain and vice-captain frequencies.
15. **Independent solver parity** — pinned `open-fpl-solver` receives the same ensemble-mean xP used by Pinnacle and checks the independent mathematical formulation.
16. **Personal weekly strategy** — entry 63984 supplies the published squad/bank/FT/selling-price state. The Pinnacle transfer candidate pool protects cheap enablers, positional alternatives, price-band options, Pareto-efficient players and short-term fixture punts from naive global top-N pruning.
17. **Receding-horizon transfer policy** — optimise several weeks, execute only `action_now`, quantify the exact value lost by forcing a roll, then refresh and re-solve next deadline. Before GW1, GW2-GW5 is a contingency route only.
18. **Chip window** — Wildcard, Free Hit, Bench Boost and Triple Captain opportunity values are quantified under the 2026/27 rules. Production defaults to hold until remaining-half opportunity cost is calibrated.
19. **No-hindsight learning archive** — the freshest green pre-deadline player forecasts are archived before each lock, official FPL outcomes are attached only after the event is finished, and walk-forward expert/calibration reports are rebuilt from genuine historical decision-time data.

## The primary decision rule

The default objective is **maximum expected FPL points**.

The deterministic full-horizon MILP is the main answer. CVaR, exact regret, expected-minutes/role confidence, source health and independent solver parity tell us how robust the answer is.

A pick is strongest when it appears in both the maximum-EV and robust solutions, banning it causes material objective regret, expected minutes/role evidence are strong, model disagreement is low and the independent formulation agrees.

A near-zero regret pick is a genuine near-tie. It should be allowed to change when new price, role, injury or press-conference information arrives.

## Before GW1

The public FPL API cannot reveal an unpublished draft. Pinnacle therefore works in initial-squad mode.

Easiest local command:

```bash
apex-fpl pinnacle --horizon 8
apex-fpl pinnacle-status
```

Equivalent explicit runner:

```bash
python scripts/run_pinnacle.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
python scripts/assert_pinnacle.py data/generated/pinnacle_latest.json
```

The final output contains unrestricted, Haaland and no-Haaland maximum-EV squads, robust CVaR versions, exact sensitivity/regret, GW1 XI, captain, vice-captain, bench order, uncertainty and source/provenance evidence.

It also contains a GW2-GW5 contingency route from the selected initial squad and a
conservative chip hold policy. Those future moves are not instructions: only the
freshly re-solved first action after the next deadline may be executed.

A dedicated final run is scheduled for the morning of **21 August 2026**.

## After each deadline

Entry 63984 is automatically synchronised from the public FPL endpoints. Apex records the latest published 15, bank, team value, captain/vice, rolled FTs, transfer history, chip history and manager-specific selling prices.

The public API is a deadline snapshot. It cannot see a transfer privately made after the latest deadline. The ideal workflow is therefore to ask Pinnacle **before** making the transfer. If a transfer was already made, provide the change as a manual override before relying on the public-state recommendation.

## Weekly operating routine

1. Let the latest injury/manager information arrive.
2. Run Apex Pinnacle or use the newest green published snapshot.
3. Read `weekly_strategy.action_now`.
4. Compare `weekly_strategy.roll_regret` against doing nothing.
5. Inspect maximum-EV/CVaR agreement and exact regret for the players involved.
6. Inspect `chip_window`; do not spend a chip just because its immediate gain is positive.
7. Execute only the current action.
8. After the deadline, refresh everything and solve again. Later transfers from the old plan were contingencies, not commitments.

## Easiest interface: ChatGPT

Ask naturally:

- `Give me the latest Apex Pinnacle team.`
- `Stress-test Haaland vs no Haaland and choose the final structure.`
- `Which picks are mathematically fragile?`
- `What is my best transfer this week?`
- `Should I roll? Show the exact expected-value cost of rolling.`
- `Is a -4 justified?`
- `Give me the action now and the contingent 3-GW path.`
- `Who should I captain and vice-captain?`
- `What is the exact bench order?`
- `Should I wildcard now or wait?`
- `What are the current chip opportunity values?`
- `Why is Player A ahead of Player B?`
- `What changed since the last green run?`
- `Does CVaR or the independent solver disagree with maximum EV?`
- `How has the model performed in the completed Gameweeks?`

ChatGPT should read `data/generated/pinnacle_latest.json` first and should never reconstruct a remembered historical squad when a current repository snapshot exists.

## GitHub-only use

To force a cloud run without installing anything:

1. Open `mcnuggets651/fpl-apex` on GitHub.
2. Open **Actions**.
3. Select **Apex Pinnacle**.
4. Click **Run workflow** and choose `main`.
5. Only use the result after the workflow finishes green.
6. Read `data/generated/pinnacle_latest.md` or ask ChatGPT for the latest Pinnacle recommendation.

The full Pinnacle workflow also runs every six hours. Independent same-surface solver parity runs on its validation cadence and is embedded back into the repository snapshot.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,airsenal]'

export FPL_ENTRY_ID=63984
export AIRSENAL_PROJECTIONS_CSV=data/generated/airsenal.csv

apex-fpl pinnacle --horizon 8
apex-fpl pinnacle-status
```

Optional environment variables:

- `APEX_NEWS_FEEDS` — additional trusted/official news sources;
- `ODDS_API_URL` / `ODDS_API_KEY` — optional market-xP feed;
- `APEX_HORIZON` — planning horizon;
- `APEX_UNDERSTAT_TEAM_MODEL_MODE` — `shadow` by default; use `production` only after a separate evidenced promotion;
- `FPL_ENTRY_ID` — personal entry (63984 in production).

## Main files

- `data/generated/pinnacle_latest.json` — machine-readable final Pinnacle decision.
- `data/generated/pinnacle_latest.md` — human-readable decision.
- `data/generated/apex_latest.json` — validated underlying production Apex state.
- `data/generated/solver_parity.json` — independent same-surface optimiser agreement.
- `data/generated/airsenal.csv` — genuine AIrsenal evidence.
- `data/generated/calibration_report.json` — season learning/backtest status.
- `data/history/deadlines/gwXX_forecast.csv` — genuine pre-deadline forecasts plus official outcomes after completion.
- `reports/pinnacle_selection_regret.csv` — exact decision sensitivity.
- `reports/pinnacle_scenario_player_summary.csv` — scenario mean/SD/P10/P50/P90.
- `reports/pinnacle_decision_frequencies.csv` — uncertainty re-solve selection frequencies.
- `reports/data_quality.csv` — field-level production checks and coverage.
- `reports/team_goal_ratings.csv` / `team_goal_surface.csv` — Understat shadow challenger outputs.
- `reports/team_state.json` — latest personal FPL state after the season begins.
- `docs/evidence/team_goal_model_2026-08-07.json` — committed chronological challenger evidence and failed promotion gate.
- `upstreams.lock.json` — exact upstream revisions.

## The learning loop

No pre-season model can train against future 2026/27 outcomes that do not yet exist. Pinnacle does not invent that evidence.

Within 30 hours of each deadline, the scheduled green run writes/refreshes the target Gameweek archive. Once Official FPL marks the Gameweek finished, the archive is completed with official points. `calibration_report.json` then reports expert error/rank metrics, a constrained candidate ensemble calibration once enough data exists, and a latest-GW walk-forward holdout check.

Weights are **not auto-promoted from one lucky sample**. Calibration remains advisory until repeated genuine out-of-sample holdouts establish a stable improvement. The same standard applies to covariance coefficients, which begin as transparent priors and can be validated as 2026/27 evidence accumulates.

## Interpretation standard

Pinnacle optimises the quality of the decision process; it cannot make football deterministic. Injuries, red cards, penalties and finishing variance remain real.

The standard is:

> Use every defensible current signal, preserve Official FPL truth, enforce the rules, maximise expected points, model correlated uncertainty, quantify regret and fallback mechanics, cross-check the optimiser, learn only from genuine pre-deadline history, and refuse to act when the gate is not green.
