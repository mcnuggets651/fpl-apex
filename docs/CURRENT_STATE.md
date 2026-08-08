# Apex FPL — Current State

**Last updated:** 2026-08-08

## Production
- Repository: `mcnuggets651/fpl-apex`
- Branch: `main`
- Personal entry: `63984`
- Pinnacle: active production decision engine
- Elite 10.0: merged to `main`
- Elite PR #6: configured `Apex FPL` CI completed successfully before merge

## Current modelling philosophy
Use Pinnacle ensemble xP as canonical expected points. Use Elite as an additional ceiling/captaincy/minutes-aware decision lens. Never assume Elite is better until the latest live output is compared with Pinnacle on raw xP.

## Elite profile
`35 attack / 20 minutes / 15 captaincy / 10 set pieces / 10 fixture / 5 bonus+DEFCON / 5 value`

## Immediate next action
Run/inspect the merged Elite 10.0 optimiser on the latest live source surface and benchmark it against current Pinnacle. Compare unrestricted, Haaland and no-Haaland scenarios before declaring a final Apex Elite squad.

## Current known boundary
- The public FPL API cannot expose an unpublished pre-deadline draft. A current screenshot/manual team can therefore be newer than entry `63984`'s public state.
- Market odds are a planned enhancement unless/until a validated feed is confirmed in the production gate.
- New-season evidence is inherently limited before competitive matches accumulate.

## Latest user objective
Prioritise the highest projected point accumulation and elite ceiling, incorporating attacking threat, expected minutes, preseason, fixtures, penalties/set pieces, clean sheets, DEFCON and bonus. Avoid the previous optimiser failure mode of over-selecting questionable low-ceiling value picks.

## Do not forget
The user has supplied a current private draft via screenshot in the active project history. It is a comparison candidate, not automatically the optimum. Future recommendations should compare the latest private/manual team with live Pinnacle/Elite outputs when available.

## Status labels
- **Production now:** Pinnacle + merged Elite code.
- **Needs validation now:** live Elite output versus Pinnacle after merge.
- **Proposed, not production:** Apex Meta selector and future market/Bayesian/ownership upgrades.
