# Apex FPL — Canonical Decision Policy

This document defines the **only user-facing team-selection policy** for Apex. Internal models may disagree, but they do not create separate recommendations.

## Canonical contract
The only published/user-facing recommendation is:

- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`

The only production command is:

```bash
python scripts/run_apex.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
```

`pinnacle_latest.*`, `elite_latest.*`, CVaR, solver parity and regret reports are **internal diagnostic/challenger evidence only**. They must never be presented as competing Apex teams.

## Unified decision hierarchy
1. Build the current canonical player/fixture universe from Official FPL.
2. Enrich with validated FPL Core, AIrsenal, historical, preseason, tactical, news and fixture evidence.
3. Produce canonical ensemble expected points (`xp`).
4. Treat expected minutes/start/appearance probabilities as first-class inputs.
5. Solve the legal maximum-xP squad over the planning horizon.
6. Run correlated uncertainty/CVaR, exact force/ban regret, captain stability and independent parity as robustness diagnostics.
7. Run Elite only as a diagnostic frontier inside a near-optimal xP set.
8. Audit Elite across epsilon = 0%, 0.25%, 0.5%, 1.0%.
9. The unrestricted rolling-horizon maximum-EV strategy is the sole canonical selection.
10. Elite convergence is evidence only and never substitutes a different production 15.
11. Re-optimise XI, captain, vice and bench mechanics on raw xP for the selected 15.
12. Publish a team only when all required readiness/snapshot-consistency gates pass.

## What does not enter the maximum-points objective
- ownership / effective ownership;
- reputation or popularity;
- a standalone value/points-per-million score;
- a standalone weighted Elite score;
- independent random-player Monte Carlo noise.

Ownership belongs only in an explicit rank-management mode, never in the pure maximum-points recommendation.

## Projection-model roadmap
The next projection upgrade is empirical-Bayes / partial-pooling shrinkage of small-sample player attacking rates toward role/position priors. This is a forecast improvement, not a competing selection philosophy.

Dixon-Coles/Poisson may later be added as a historically validated fixture expert/challenger. It does not replace the ensemble by assumption.

## ChatGPT operating rule
When the user asks for “the Apex team”, “best team”, “recommendation”, or equivalent:

1. Load the Project Brain.
2. Read `data/generated/apex_recommendation_latest.json` first.
3. If `ready_to_act` is false, report the blockers instead of inventing a team.
4. If true, present that team as **the** Apex recommendation.
5. Use internal Pinnacle/Elite/CVaR outputs only to explain why the canonical decision was selected or to diagnose fragility.

No alternative Apex squad should be presented unless the user explicitly asks for a scenario such as “force Haaland” or “show me no-Haaland”. Even then, label it as a scenario, not a second recommendation.
