# Apex FPL — Model Specification

## Canonical expected points
`xp` is the ensemble-mean expected FPL points for a player in a Gameweek. The underlying transparent decomposition includes, where applicable:
- expected minutes / appearance
- attacking xG/xA/xGI
- clean-sheet expectation
- goalkeeper saves
- defensive contributions (DEFCON)
- penalties and set pieces
- tactical role
- bonus/BPS prior

The projection surface also carries uncertainty/disagreement information and floor/ceiling estimates.

## Pinnacle objective
Primary objective: maximise expected FPL points on ensemble mean `xp`, subject to legal FPL squad, budget, club and formation constraints. Risk is evaluated separately through stochastic scenarios/CVaR and exact selection regret.

## Elite 10.0 utility
Elite is a decision utility, not a new xP forecast.

`Elite = .35 Attack + .20 Minutes + .15 Captaincy + .10 SetPieces + .10 Fixture + .05 BonusDefcon + .05 Value`

Weights must sum to 1.0.

### Attack — 35%
Current implementation combines position-relative ranks of:
- 55% `xp_attack`
- 20% model xG/90
- 10% model xA/90
- 10% shots signal
- 5% big-chances signal

### Minutes — 20%
- 50% expected minutes / 90
- 35% start probability
- 15% appearance probability

### Captaincy — 15%
- 65% rank of canonical `xp`
- 35% rank of 80th-percentile projection ceiling

This is the explicit premium-ceiling correction.

### Set pieces and penalties — 10%
Raw role signal:
- 60% penalty share
- 15% corner share
- 15% direct free-kick share
- 10% indirect free-kick share

The current implementation blends this 75/25 with the set-piece xP prior.

### Fixture — 10%
Position-relative rank of match-specific `xp_attack + xp_clean_sheet`. This deliberately reuses the transparent projection's fixture translation rather than creating an undocumented second fixture model.

### Bonus + DEFCON — 5%
Equal blend of position-relative bonus/BPS prior and defensive-contribution xP.

### Value — 5%
Position-relative rank of `xp / price`. This is intentionally small: value may break ties but cannot dominate Elite selection.

## Normalisation
Most Elite components use per-Gameweek percentile ranks, often within FPL position, to make unlike metrics comparable. Elite score is clipped to [0,1].

## Required comparison
For every Elite candidate squad report:
- Elite utility/objective
- raw ensemble xP over the same horizon
- raw-xP regret versus maximum-EV Pinnacle
- captaincy difference
- major minutes/role risks
- scenario differences where material

## Promotion standard
Do not change weights because a preferred player is missing. Weight or feature changes require a benchmark hypothesis, no-hindsight evaluation where possible, and a recorded decision in `APEX_DECISIONS.md`.
