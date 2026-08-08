# Apex FPL — Current State

**Last updated:** 2026-08-08

## Production
- Repository: `mcnuggets651/fpl-apex`
- Branch: `main`
- Personal entry: `63984`
- Pinnacle: active production decision engine
- Elite 10.0: live, with xP-anchored correction currently under validation
- Prior-season evidence/captain-stability blockers: resolved by PR #10 and green on main

## Current modelling philosophy
Pinnacle ensemble `xp` is canonical expected points. Elite is a controlled ceiling/captaincy/minutes-aware decision modifier around that forecast, never an alternative synthetic points model. Every Elite candidate is re-scored on raw xP.

## Elite profile
Evidence weights: `35 attack / 20 minutes / 15 captaincy / 10 set pieces / 10 fixture / 5 bonus+DEFCON / 5 value`.

Validated correction: the evidence score must not be optimised as standalone percentile utility. The corrected Elite surface anchors on raw xP and applies a bounded ±5% modifier. The cap is deliberately conservative and requires benchmark evidence before expansion.

## Immediate next action
Validate the xP-anchored Elite correction in CI, merge if green, then run one synchronized live snapshot producing Pinnacle maximum-EV, Elite unrestricted, Elite Haaland and Elite no-Haaland candidates. Compare all candidates on raw xP, captaincy, minutes, attacking ceiling, set pieces, fixtures, DEFCON/bonus and uncertainty before declaring the final Apex squad.

## Current known boundary
- The public FPL API cannot expose an unpublished pre-deadline draft. A current screenshot/manual team can therefore be newer than entry `63984`'s public state.
- Market odds remain optional unless/until a validated feed is confirmed in the production gate.
- New-season evidence is inherently limited before competitive matches accumulate.

## Latest user objective
Prioritise the highest projected point accumulation and elite ceiling, incorporating attacking threat, expected minutes, preseason, fixtures, penalties/set pieces, clean sheets, DEFCON and bonus. Avoid low-ceiling value flooding and do not sacrifice material expected points merely to improve a rank-based utility score.

## Do not forget
The user has supplied a current private draft via screenshot in the active project history. It is a comparison candidate, not automatically the optimum. Future recommendations should compare the latest private/manual team with synchronized live Pinnacle/Elite outputs.

## Status labels
- **Production now:** Pinnacle + Elite pipeline + resolved evidence/captain gates.
- **Validation now:** xP-anchored Elite objective correction.
- **Next:** synchronized Pinnacle/Elite/Haaland/no-Haaland run and final squad decision.
- **Proposed, not production:** Apex Meta selector and future market/Bayesian/ownership upgrades.
