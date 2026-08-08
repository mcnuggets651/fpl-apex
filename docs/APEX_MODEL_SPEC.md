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

## Minutes submodel
Expected minutes is a first-class model input rather than a simple historic average. The current `minutes_profile` combines:
- prior-season start probability and minutes per match
- current-season team matches, starts and minutes
- preseason appearances, starts and minutes
- official availability/chance-of-playing status
- manual and news availability multipliers
- start, appearance, 60+ and 80+ probabilities
- an explicit minutes-confidence score

Minutes can be calibrated further, but it already has an independent modelling layer and directly scales attacking, clean-sheet, save and DEFCON expectation.

## Player attacking rates
The transparent player model currently uses direct player rates such as xG90/xA90 and blends preseason observations according to preseason minutes. This is preferable to allocating team xG by a single historical player share, but it still has a small-sample weakness.

### Planned shrinkage upgrade
Implement empirical-Bayes / partial-pooling shrinkage for player attacking rates:
- derive position/role priors;
- weight player-specific evidence by sample minutes / event volume;
- shrink small-sample xG90/xA90/shooting rates toward the relevant prior;
- retain more player-specific signal as evidence volume grows;
- benchmark out of sample in the no-hindsight archive before promotion.

This upgrade takes priority over adding a new Dixon-Coles fixture expert because rate uncertainty directly affects every player projection.

## Elite 10.0 secondary utility
Elite is a secondary decision utility, not a new xP forecast.

`Elite = .35 Attack + .20 Minutes + .15 Captaincy + .10 SetPieces + .10 Fixture + .05 BonusDefcon + .05 Value`

Weights must sum to 1.0.

### Lexicographic selection rule
Elite uses an epsilon-constraint design:
1. solve the relevant scenario for maximum raw Pinnacle `xp`;
2. define a near-optimal raw-xP floor;
3. maximise Elite utility only among solutions satisfying that floor;
4. lock the selected 15;
5. re-optimise XI, captain and vice on raw `xp`.

The default regret allowance is 0.5%, but this is explicitly provisional rather than calibrated.

### Epsilon sensitivity
Every live Elite run must also report the unrestricted frontier at:
- 0.00% raw-xP regret allowance
- 0.25%
- 0.50%
- 1.00%

For each point, report raw xP, exact regret, squad overlap/change versus maximum-EV and captain. If very small epsilon changes produce materially different squads, maximum-EV remains the canonical recommendation until no-hindsight evidence establishes a justified regret band.

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

This is the explicit premium-ceiling correction, but it is only secondary to the raw-xP floor.

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
Position-relative rank of `xp / price`. This is intentionally small and only influences near-optimal xP solutions.

## Team-strength experts
The current production fixture layer uses validated internal strength evidence and fallback logic. A future Dixon-Coles/Poisson model should be added only as an independent expert/challenger, trained with recency weighting and evaluated out of sample.

Do not naively average future fixture experts. Any combination of Dixon-Coles, xG-based ratings, Elo and market odds must use an explicit historically validated combination rule or stacking procedure. Until that exists, disagreement should be surfaced rather than hidden inside undocumented weights.

## Ownership
Ownership/EO is not part of the canonical maximum-points objective. It may be introduced only in a separate rank-management mode or documented tiebreak where the optimisation target explicitly changes from points to rank utility.

## Uncertainty
Scenario simulation should preserve correlated football outcomes: team attack/defence, opponents, player returns and minutes/rotation are not independent. Apex uses correlated stochastic scenarios, CVaR and exact regret rather than independent draws around each player's mean.

## Required comparison
For every Elite candidate report:
- maximum raw ensemble xP reference
- Elite-selected squad raw xP
- exact raw-xP regret
- epsilon sensitivity frontier
- captaincy difference
- major minutes/role risks
- scenario differences where material

## Promotion standard
Do not change weights, epsilon, priors or feature rules because a preferred player is missing. Changes require a benchmark hypothesis, no-hindsight evaluation where possible, and a recorded decision in `APEX_DECISIONS.md`.
