# Apex FPL — Unified Decision Engine

Apex is a reproducible 2026/27 Fantasy Premier League decision system built to answer one question:

> Given everything we can defensibly know before the deadline, what is the single legal FPL decision that best maximises expected points, and how robust is it?

Production personal entry: **63984**.

## One team, one contract

Apex no longer exposes Pinnacle, Elite, CVaR, value or other models as competing user-facing teams.

The **only** user-facing recommendation is:

- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`

The **only** production command is:

```bash
python scripts/run_apex.py \
  --horizon 8 \
  --stochastic-scenarios 256 \
  --cvar-alpha 0.10 \
  --cvar-weight 0.20 \
  --force
```

The runner fetches and projects once into a content-addressed sealed decision
bundle. Pinnacle, Elite and the canonical builder must all carry the same
`bundle_id`; see `docs/DECISION_BUNDLE.md` for lineage audit and offline replay.

If `ready_to_act` is false, Apex withholds a team and reports the blockers instead of choosing manually among diagnostic outputs.

## Canonical decision policy

The production hierarchy is:

1. Official FPL canonical identity/price/status/fixtures.
2. Validated FPL Core, AIrsenal, historical, preseason, tactical, news and fixture evidence.
3. First-class expected-minutes/start/appearance model.
4. Canonical ensemble expected points (`xp`).
5. Legal maximum-xP MILP shortlist inside a disclosed near-optimal band.
6. Correlated scenario/CVaR, exact regret, captain stability and independent-solver diagnostics.
7. Elite 35/20/15/10/10/5/5 as a diagnostic frontier inside a near-optimal xP set.
8. Epsilon frontier at 0%, 0.25%, 0.5% and 1.0%.
9. Exact XI/captain/vice/bench/autosub rescoring across every horizon Gameweek produces the sole canonical `Decision`.
10. Elite convergence cannot substitute a different production 15.
11. Near-equivalent candidates are disclosed and Apex does not claim an unproven unique optimum.
12. Publish one recommendation only when readiness and snapshot-consistency gates are green.

Full policy: [`docs/APEX_CANONICAL_DECISION_POLICY.md`](docs/APEX_CANONICAL_DECISION_POLICY.md).

## Internal diagnostics — not separate recommendations

The following remain important, but are internal evidence layers:

- `pinnacle_latest.*` — maximum-EV and production-readiness diagnostics.
- `elite_latest.*` — epsilon/lexicographic secondary-selector diagnostics.
- correlated CVaR solution — lower-tail sensitivity.
- exact force/ban regret — selection fragility.
- captain/vice/autosub mechanics — deadline execution.
- independent solver parity — same-surface optimisation check.
- Haaland/no-Haaland scenarios — explicit counterfactuals.

Historical standalone selection philosophies are documented under `archive/selection_approaches/` and must not be presented as alternative Apex teams.

## What Apex uses

- **Official FPL** — player identity, club, position, price, status, fixtures.
- **FPL Core Insights** — underlying stats, preseason, Elo/strength, defensive-contribution context.
- **Pinned AIrsenal** — independent expected-points expert mapped through Official FPL IDs.
- **Apex xP decomposition** — minutes, attack, clean sheets, saves, DEFCON, penalties/set pieces, tactical role, bonus/BPS.
- **News/manager/transfer evidence** — availability and role verification.
- **Projection ensemble** — mean xP, disagreement, confidence, variance, floor/ceiling.
- **Correlated stochastic scenarios** — team/player/minutes outcome dependence.
- **Receding-horizon transfer planning** — execute the current action, then refresh and re-solve.
- **No-hindsight archive** — pre-deadline forecasts stored before outcomes are known.

Exact external revisions are pinned in `upstreams.lock.json`.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,airsenal]'
export FPL_ENTRY_ID=63984
python scripts/run_apex.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
```

Then read:

```text
data/generated/apex_recommendation_latest.json
```

## ChatGPT operating rule

When the user asks:

> “Give me the Apex team.”

ChatGPT must:

1. load the Project Brain;
2. read `apex_recommendation_latest.json` first;
3. present that recommendation if `ready_to_act=true`;
4. otherwise report blockers;
5. use Pinnacle/Elite/CVaR only to explain the canonical decision;
6. never produce several competing Apex teams unless the user explicitly asks for a labelled scenario.

## Project Brain

Start with:

1. [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md)
2. [`docs/APEX_MASTER_CONTEXT.md`](docs/APEX_MASTER_CONTEXT.md)
3. [`docs/APEX_DECISIONS.md`](docs/APEX_DECISIONS.md)
4. [`docs/APEX_CANONICAL_DECISION_POLICY.md`](docs/APEX_CANONICAL_DECISION_POLICY.md)
5. [`docs/APEX_OPERATING_MANUAL.md`](docs/APEX_OPERATING_MANUAL.md)

## Current modelling priority

The next forecast-model upgrade is **empirical-Bayes / partial-pooling shrinkage of small-sample player xG90/xA90 and related rates toward role/position priors**. This improves the canonical xP forecast; it does not create another selection philosophy.

Dixon-Coles/Poisson is a later fixture-expert benchmark and must earn ensemble weight through historical validation.

## Known boundary

Apex improves decision quality; it cannot remove football randomness. Before enough 2026/27 outcomes exist, some covariance/minutes/rate assumptions remain priors and are explicitly tracked for calibration.

The standard is not certainty. The standard is **one consistent, auditable decision from the strongest validated process available**.

## Licence

Apex itself is MIT. External workers keep their own licences and are not vendored into this repository.
