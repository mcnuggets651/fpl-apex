# Apex FPL — Unified Decision Engine

Apex is a reproducible 2026/27 Fantasy Premier League decision system built to answer one question:

> Given the strongest defensible pre-deadline evidence, what is the single legal FPL action that best maximises expected points, and how robust is it?

Production personal entry: **63984**.

## One recommendation, one contract

Apex does not expose Pinnacle, Elite, CVaR, value or shadow models as competing user-facing teams.

The only user-facing decision files are:

- `data/generated/apex_answer_context.json`
- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`

If `safe_to_act=false` or `ready_to_act=false`, Apex has no actionable recommendation and must report the blockers instead of resurrecting an older squad.

## Production authority

Current production authority is deliberately separated by capability:

1. **Official FPL — factual truth:** current player ID, club, FPL position, price, Official status and fixtures.
2. **AIrsenal — statistical xP:** canonical production `xp` equals validated AIrsenal xP exactly. Missing/stale/incomplete AIrsenal blocks; Apex does not silently fall back to its own model.
3. **Current football evidence — role/availability context:** injuries, suspensions, transfers, lineups and set pieces are attributable, freshness-bounded inputs.
4. **Apex — decision engine:** legal optimisation, current manager state, exact XI/captain/vice/bench/autosubs, solver parity, robustness and receding-horizon first-action selection.
5. **Apex proprietary xP, FPL Core, Understat and other challengers — shadow/enrichment:** useful for evidence and future learning, but not current production forecast authority.
6. **Prospective calibration — promotion judge:** future forecast authority must be earned from frozen-before-deadline evidence and later Official outcomes.

The previous fixed Apex/Official-EP/AIrsenal production blend is retired.

## Production command

```bash
python scripts/run_apex.py \
  --horizon 8 \
  --stochastic-scenarios 256 \
  --cvar-alpha 0.10 \
  --cvar-weight 0.20 \
  --force
```

The runner seals one DecisionBundle. Internal diagnostics must consume that same surface rather than independently refetching live inputs.

## Current strategy mode

GW1 is complete. Normal production uses `receding_horizon_current_team_maximum_ev`: start from the exact current squad, bank, realised selling values and free transfers, solve the legal future option set, and publish only the first currently executable action.

The historical `adaptive_gw1_launch_with_transfer_option_value` selector remains for replay/history. The one-off GW1 workflow is archived and no longer active.

## Internal diagnostics — not separate recommendations

Apex retains:

- static exact-horizon/Pinnacle surfaces;
- Elite epsilon frontier;
- correlated CVaR scenarios;
- exact force/ban regret;
- captain/vice/bench/autosub mechanics;
- independent solver parity;
- Apex proprietary/shadow projection surfaces;
- forced scenarios such as Haaland/no-Haaland when explicitly requested.

These layers challenge the decision and reveal fragility. They cannot independently set publication authority.

## Source roles

- **Official FPL:** factual universe and current prices/fixtures.
- **Pinned AIrsenal:** current production statistical xP provider.
- **FPL Core Insights:** validated enrichment for player/preseason/Elo/DEFCON context.
- **Understat:** underlying-stat enrichment and shadow modelling.
- **News/manager/transfer evidence:** current availability and role verification.
- **Historical datasets:** priors, replay and prospective evaluation support.
- **Independent solvers:** optimisation assurance on the same sealed xP surface.

Exact governed revisions are recorded in `upstreams.lock.json`.

## Prospective learning

Production and shadow forecasts are intended to be frozen before each deadline and joined to Official outcomes only after the event. No challenger can be promoted from hindsight.

Current governance requires at least 8 genuine completed Gameweeks and >=200 active rows plus chronological/Gameweek-block/cohort evaluation and explicit review before forecast authority can change. The 28 August 2026 audit found that this deadline archive is not yet operating correctly and calibration still has zero completed genuine Gameweeks, so Apex proprietary xP remains shadow-only.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,airsenal]'
export FPL_ENTRY_ID=63984
python scripts/run_apex.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
```

Then inspect `data/generated/apex_answer_context.json` first.

## ChatGPT operating rule

When asked for the Apex team/action:

1. load the Project Brain/current state;
2. read `apex_answer_context.json` first;
3. verify freshness, bundle/snapshot identity and final gates;
4. present `production_result` only when safe/actionable;
5. otherwise report blockers;
6. never construct a competing squad from chat memory, generic web lists or stale diagnostics.

## Project Brain

Start with:

1. [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md)
2. [`docs/APEX_MASTER_CONTEXT.md`](docs/APEX_MASTER_CONTEXT.md)
3. [`docs/APEX_DECISIONS.md`](docs/APEX_DECISIONS.md)
4. [`docs/APEX_CANONICAL_DECISION_POLICY.md`](docs/APEX_CANONICAL_DECISION_POLICY.md)
5. [`docs/APEX_OPERATING_MANUAL.md`](docs/APEX_OPERATING_MANUAL.md)

## V2 boundary

Draft PRs #67–#88 are a separate withheld V2 programme. Their later heads still contain the retired fixed forecast-blend assumption, so they must be rebased/requalified against current authority before any future production merge. PR #66 is superseded V1 archaeology/regression material and must not be merged.

## Standard

Apex cannot remove football randomness. The standard is a single, current, legal and auditable decision produced from correctly governed factual truth, statistical forecasts, evidence and exact FPL mechanics.

## Licence

Apex itself is MIT. External workers retain their own licences and are not vendored into this repository.
