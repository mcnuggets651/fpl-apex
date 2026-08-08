# Apex FPL — Current State

**Last updated:** 2026-08-08

## Production
- Repository: `mcnuggets651/fpl-apex`
- Branch: `main`
- Personal entry: `63984`
- Pinnacle: active production decision engine
- Elite 10.0: live code, with xP-first lexicographic correction under validation in PR #11
- Prior-season evidence/captain-stability blockers: resolved by PR #10 and green on main

## Current modelling philosophy
Canonical team selection is probabilistic expected-points first. Pinnacle ensemble `xp` is the forecast and primary optimisation surface. Alternative preferences such as attacking ceiling, minutes security, captaincy, set pieces, fixtures, bonus/DEFCON and value must not silently become a second points forecast.

## Elite profile
Evidence weights remain: `35 attack / 20 minutes / 15 captaincy / 10 set pieces / 10 fixture / 5 bonus+DEFCON / 5 value`.

Elite is now designed as a secondary objective under an xP floor:
1. solve maximum raw xP for the relevant scenario;
2. retain only solutions within 0.5% of that maximum objective;
3. maximise Elite utility inside that near-optimal band;
4. lock the selected 15 and re-optimise XI, captain and vice on raw xP.

The 0.5% regret band is provisional and must be benchmarked rather than expanded to force preferred players.

## Architecture review — 2026-08-08
A proposed two-stage approach (team-strength model -> player xPts -> constrained optimiser -> uncertainty simulation) was reviewed. Apex agrees with the core xPts-first principle but does not adopt the proposal literally:
- Dixon-Coles/Poisson should be an independent fixture expert/challenger, not the sole team-strength truth.
- Player xPts should use direct player rates, expected minutes, role, set pieces and opponent effects; do not allocate team xG mechanically by a single historical share.
- Ownership is excluded when the objective is maximum FPL points. Use it only for an explicit rank-management/tiebreak mode.
- Uncertainty must preserve correlated team/player/minutes outcomes rather than sample independent noise around player means.

## Immediate next action
Validate PR #11 CI with the lexicographic correction. If green, merge it and run one synchronized live snapshot producing Pinnacle maximum-EV, Elite unrestricted, Elite Haaland and Elite no-Haaland candidates. Compare them on raw xP, captaincy, minutes, attack, set pieces, fixtures, DEFCON/bonus and stochastic robustness before declaring the final Apex squad.

## Current known boundary
- The public FPL API cannot expose an unpublished pre-deadline draft. A current screenshot/manual team can therefore be newer than entry `63984`'s public state.
- Market odds remain optional unless/until a validated feed is confirmed in the production gate.
- New-season evidence is inherently limited before competitive matches accumulate.
- A Dixon-Coles/Poisson fixture component is a planned benchmark candidate, not yet a replacement for the current ensemble fixture layer.

## Latest user objective
Prioritise the highest projected point accumulation and elite ceiling, incorporating attacking threat, expected minutes, preseason, fixtures, penalties/set pieces, clean sheets, DEFCON and bonus. Avoid low-ceiling value flooding and do not sacrifice material expected points merely to improve a rank-based utility score.

## Do not forget
The user has supplied a current private draft via screenshot in the active project history. It is a comparison candidate, not automatically the optimum. Future recommendations should compare the latest private/manual team with synchronized live Pinnacle/Elite outputs.

## Status labels
- **Production now:** Pinnacle + Elite pipeline + resolved evidence/captain gates.
- **Validation now:** PR #11 lexicographic xP-first Elite correction.
- **Next:** synchronized Pinnacle/Elite/Haaland/no-Haaland run and final squad decision.
- **Planned benchmark:** Dixon-Coles/Poisson fixture expert against existing fixture ensemble.
- **Proposed, not production:** Apex Meta selector and future market/Bayesian/ownership-rank upgrades.
