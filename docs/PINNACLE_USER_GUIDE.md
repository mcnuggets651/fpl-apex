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
4. **Apex transparent xP** — expected minutes, xG/xA/xGI, fixture strength, tactical role, clean sheets, saves, defensive contributions, set pieces, penalties and 2026/27 bonus/BPS.
5. **Trusted news/availability layer** — injuries, return dates, transfer uncertainty and manager/line-up evidence. It cannot overwrite Official FPL identity.
6. **Ensemble** — combines available projection experts, reports disagreement, standard deviation, floors/ceilings and confidence.
7. **Maximum-EV full-horizon MILP** — fixed initial 15, legal XI and captain optimised separately in every Gameweek over the horizon. This uses ensemble mean xP, not a hidden risk penalty.
8. **Correlated scenario model** — team attack/defence, opponent and player uncertainty are stressed jointly rather than pretending assets are independent.
9. **CVaR MILP** — a second solution balances mean return with lower-tail robustness. It is evidence about fragility, not an instruction to blindly choose the safest team.
10. **Exact selection regret** — every selected player is removed and the problem is re-solved; strong alternatives are forced and re-solved. This quantifies how costly a change really is.
11. **Exact deadline mechanics** — captain/vice no-show fallback and the optimal outfield bench order are evaluated explicitly. Autosubs enumerate the relevant binary appearance states subject to legal FPL formation rules.
12. **Independent solver parity** — the pinned open-fpl-solver checks whether an independent formulation agrees with the same Apex projection surface.
13. **Personal weekly strategy** — after a public deadline squad exists for entry 63984, Apex reads the squad/bank/FT state and uses receding-horizon transfer planning: execute only the first action, then re-solve after new information arrives.
14. **Chip window** — current Wildcard, Free Hit, Bench Boost and Triple Captain opportunity values are quantified under the 2026/27 chip rules. Positive current value is not enough by itself to burn a chip; future opportunity cost is retained.

## The primary decision rule

The default objective is **maximum expected FPL points**.

Pinnacle does not lower the expected-value target simply to make a team look safer. The deterministic full-horizon MILP is the main answer. The CVaR solution, exact regret, source confidence and solver parity tell us whether that answer is robust.

A pick is strongest when:

- it appears in the deterministic optimum;
- it also appears in the CVaR optimum;
- banning it creates material objective regret;
- expected minutes and role confidence are high;
- model disagreement is low;
- independent solver evidence agrees.

A pick with near-zero regret should be treated as a near-tie and can legitimately change after one new press conference, price move or role update.

## Before GW1

The public FPL API cannot reveal an unpublished draft. Pinnacle therefore works in initial-squad mode.

Run:

```bash
python scripts/run_pinnacle.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
python scripts/assert_pinnacle.py data/generated/pinnacle_latest.json
```

The final output contains:

- unrestricted maximum-EV squad;
- Haaland-locked squad;
- no-Haaland squad;
- robust CVaR versions;
- expected-value/robust overlap;
- exact selection regret;
- GW1 XI;
- exact captain and vice-captain recommendation;
- exact outfield bench order;
- projection uncertainty and source health.

A dedicated final run is scheduled for the morning of **21 August 2026**.

## After each deadline

Entry 63984 is automatically synchronised from the public FPL endpoints. Apex records:

- latest published 15;
- bank;
- team value;
- captain and vice;
- available rolled free transfers;
- transfer history;
- chip history;
- reconstructed manager-specific selling prices.

The public API is a deadline snapshot. It cannot see a transfer you privately make after the latest deadline. Therefore the ideal workflow is to ask Apex **before** making the transfer. If you already made one, provide the change as a manual override before relying on the recommendation.

## Weekly operating routine

The preferred routine is:

1. Wait for the latest injury/manager information available before the deadline.
2. Run Apex Pinnacle or use the newest green published snapshot.
3. Inspect `weekly_strategy.action_now`.
4. Compare `weekly_strategy.roll_regret` to the recommended transfer.
5. Check the deterministic/CVaR agreement and selection regret for players involved.
6. Check `chip_window`, but spend a chip only when its current advantage also makes sense against future opportunity cost.
7. Execute only the current action.
8. After the deadline, refresh the model and re-solve. Future transfers in the previous plan were contingencies, not commitments.

## Easiest way to use it: ChatGPT

Ask naturally. Examples:

- `Give me the latest Apex Pinnacle team.`
- `Stress-test Haaland vs no Haaland and choose the final structure.`
- `Which three picks are most fragile?`
- `What is my best transfer this week?`
- `Should I roll the transfer? Show the exact value of rolling.`
- `Is a -4 justified?`
- `Give me the best action now and the contingent 3-GW path.`
- `Who should I captain and vice-captain?`
- `What is the exact bench order?`
- `Should I wildcard now or wait?`
- `What are the current Bench Boost / Triple Captain / Free Hit opportunity values?`
- `Why is Player A ahead of Player B?`
- `What changed since the last green run?`
- `Does CVaR or the independent solver disagree with the maximum-EV team?`

ChatGPT should read `data/generated/pinnacle_latest.json` first. It should never reconstruct a remembered squad when a current repository snapshot is available.

## GitHub-only use

To force a fresh cloud run without installing anything locally:

1. Open the repository on GitHub.
2. Open **Actions**.
3. Select **Apex Pinnacle**.
4. Choose **Run workflow** on `main`.
5. Wait for the workflow to finish green.
6. Read `data/generated/pinnacle_latest.md` or ask ChatGPT for the latest recommendation.

The workflow also runs every six hours.

## Local use

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,airsenal]'

export FPL_ENTRY_ID=63984
export AIRSENAL_PROJECTIONS_CSV=data/generated/airsenal.csv

python scripts/run_pinnacle.py --horizon 8 --force
python scripts/assert_pinnacle.py
```

Optional environment variables:

- `APEX_NEWS_FEEDS` — comma-separated additional trusted/official sources;
- `ODDS_API_URL` / `ODDS_API_KEY` — optional market-xP feed using the documented adapter contract;
- `APEX_HORIZON` — planning horizon;
- `FPL_ENTRY_ID` — personal entry (63984 in production).

## Main files to inspect

- `data/generated/pinnacle_latest.json` — machine-readable final Pinnacle decision.
- `data/generated/pinnacle_latest.md` — human-readable final Pinnacle decision.
- `data/generated/apex_latest.json` — validated underlying production Apex snapshot.
- `data/generated/solver_parity.json` — independent optimiser agreement.
- `data/generated/airsenal.csv` — genuine AIrsenal evidence.
- `reports/pinnacle_selection_regret.csv` — exact decision sensitivity.
- `reports/pinnacle_scenario_player_summary.csv` — scenario mean/SD/P10/P50/P90.
- `reports/team_state.json` — latest personal FPL state after the season begins.
- `upstreams.lock.json` — exact upstream source versions.

## What still learns during the season

No pre-season model can calibrate itself against future 2026/27 outcomes that do not exist yet. The covariance coefficients are therefore transparent priors initially and are reported as such. As genuine deadline/outcome history accumulates, the existing walk-forward calibration framework can update expert weights and validate covariance assumptions without using hindsight-contaminated features.

This is a **known-data limitation**, not a missing GW1 input that can be solved by inventing numbers.

## Interpretation standard

Pinnacle optimises the quality of the decision process; it cannot make football deterministic. A player can still be injured in the warm-up, a penalty can be missed and a 0.2 xG shot can go in.

The correct standard is therefore:

> Use every defensible current signal, enforce the rules exactly, maximise expected points, quantify uncertainty and regret, cross-check the optimiser, and refuse to act when the production gate is not green.
