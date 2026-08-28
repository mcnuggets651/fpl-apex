# Apex FPL — Model Specification

## Canonical expected points

Current production `xp` is the validated **AIrsenal expected FPL points** for the Official FPL player/Gameweek target. Production authority is one-hot by design until prospective evidence justifies a change:

- `airsenal = 1.0`
- `apex_model = 0.0`
- `official_ep = 0.0`
- `market = 0.0`

This is an authority contract, not a claim that AIrsenal is permanently unbeatable. It prevents subjective hand-tuned averaging before Apex has genuine out-of-sample evidence.

In production mode:

- `xp == production_xp == airsenal_xp`;
- `apex_shadow_xp` preserves the proprietary Apex forecast for comparison;
- missing/stale AIrsenal does not fall back to Apex;
- disagreement/uncertainty surfaces remain diagnostics rather than alternate authority.

## Apex proprietary forecast — shadow

Apex still computes a transparent football model using, where applicable:

- expected minutes / appearance probabilities;
- xG/xA attacking rates and priors;
- clean-sheet expectation;
- goalkeeper saves;
- defensive contributions (DEFCON);
- penalties/set-piece context;
- tactical role;
- bonus/BPS priors;
- FPL Core/Understat/historical/preseason enrichment.

These outputs are research/shadow evidence until promoted through prospective evaluation. They may challenge AIrsenal and help diagnose football assumptions, but they may not overwrite canonical production xP merely because a result looks more plausible.

## Decision objective

Apex's production decision engine maximises expected FPL points on canonical `xp`, subject to exact legal FPL constraints and current manager state. The optimiser—not the proprietary forecast—is Apex's production decision authority.

Risk/robustness is assessed separately through correlated scenarios, CVaR, exact selection regret, captain/bench mechanics and independent parity. These surfaces expose fragility without silently replacing the EV objective.

## Minutes and role modelling

Apex's minutes model remains a first-class shadow/challenger component and a supporting evidence surface. It tracks expected minutes, start/appearance/60+/80+ probabilities and confidence using historical/current samples, preseason participation, Official status and current attributable evidence.

The EV-first eligibility rule prevents double-counting minutes security. Ordinary forecast uncertainty is priced in expected outcomes/scenarios; only attributable adverse evidence can hard-exclude a player from XI/captain eligibility.

Manual/current overrides require explicit provenance and must remain bounded by Official adverse availability/suspension facts. Future minutes cannot be represented as literal certainty without deterministic factual grounds.

## Player attacking rates and shrinkage

Apex shadow rates may use direct player xG90/xA90 and governed shrinkage/priors. Small-sample behaviour must be evaluated prospectively rather than promoted because it improves a retrospective or preferred-player result.

DEFCON, Bayesian shrinkage, Understat-derived priors and similar components remain shadow/research unless a formal promotion decision authorizes production use.

## Team/fixture modelling

Official fixtures are factual truth. Internal team-strength, FPL Core Elo, Understat and other fixture-strength models are supporting/shadow models, not current canonical statistical xP authority.

A future Dixon-Coles/Poisson, market or alternative fixture expert may be evaluated as a challenger. It may enter production only after bounded prospective evidence and explicit dependency/authority changes.

## Elite secondary utility

Elite remains a diagnostic near-optimal utility, not an xP forecast and not a second user-facing selector. Historical feature weights may be retained for research regression, but they have no authority to override canonical expected points.

The epsilon frontier exists to show whether near-equivalent EV squads differ materially. It does not justify a subjective final squad when the canonical policy has not selected it.

## Ownership and price movement

Ownership/EO is excluded from the pure maximum-points objective. It may exist only in an explicitly different rank-utility mode.

Price-change forecasts may be retained as planning context but may not overwrite current Official price. Speculative future price value requires explicit modelling and validation before it affects the production objective.

## Uncertainty

Football outcomes are correlated. Robustness simulation should preserve team/opponent/minutes dependence rather than draw independent player noise. Sampling/convergence requirements remain diagnostics and release checks where required.

## Prospective provider evaluation

Production and shadow provider forecasts must be frozen before deadlines. Evaluation later joins Official outcomes against the exact frozen provider/version/snapshot/player/GW rows.

Promotion requires the governed prospective threshold, currently at least:

- 8 genuine completed Gameweeks;
- 200 active rows;
- chronological/walk-forward comparison;
- Gameweek-block confidence/uncertainty analysis;
- cohort diagnostics;
- source/feature ablation where material;
- explicit human/governance review.

No automatic promotion occurs. At the 28 August 2026 audit the genuine calibration report had zero completed Gameweeks and zero active rows, so Apex proprietary xP and all alternative blends remain unqualified for production forecast authority.

## Promotion standard

Do not change provider weights, thresholds, priors, evidence rules or named-player behaviour because a preferred squad is missing. A production change requires:

1. a precise benchmark hypothesis;
2. frozen no-hindsight challenger evidence;
3. predictive and decision-level evaluation;
4. regression/adversarial tests;
5. recorded governance decision;
6. fresh production certification after merge.
