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

## Core modelling principle
Forecast first, optimise second. Selection preferences must not be smuggled into the expected-points forecast.

The canonical architecture is:
1. team/fixture scoring environment;
2. player-level expected minutes and event rates;
3. FPL scoring translation into per-player/per-GW xPts;
4. projection ensemble and uncertainty;
5. legal squad optimisation on xPts;
6. secondary/robustness decisions only after the xPts optimum is known.

## Team / fixture scoring environment
Apex may combine multiple fixture experts. Dixon-Coles/Poisson is a valid benchmark or ensemble component because it produces coherent goal-count and clean-sheet probabilities from attack/defence strengths with recency weighting. It is not accepted as the sole truth because early-season data, promoted clubs, tactical changes, transfers and lineup quality can make historical goals alone stale.

Preferred hierarchy:
- validated current fixture model / Elo evidence;
- historical goals/xG with recency weighting;
- Dixon-Coles/Poisson challenger or ensemble expert;
- Understat and market-implied expectations when healthy and validated.

No fixture expert may silently override official identities/fixtures.

## Player attacking expectation
Do not allocate team expected goals mechanically by one historical player share. Player attacking expectation should use direct player evidence where available:
- xG/90 and xA/90
- shots / shots in box
- big chances
- starts and minutes
- tactical role / position
- penalties and set-piece shares
- opponent and team scoring environment
- preseason/current-role evidence with appropriate uncertainty

Team expected goals constrain the scoring environment, but player rates remain player-specific and may be shrunk toward team/role priors when sample sizes are weak.

## Minutes model
Expected minutes, start probability and appearance probability are first-class inputs. Rotation is represented as uncertainty, not hidden inside a single per-90 rate.

## FPL scoring translation
Translate player event probabilities into official position-specific scoring routes, including:
- appearance points
- goals and assists
- clean sheets by position
- goalkeeper saves
- bonus/BPS prior
- defensive contributions / DEFCON where applicable
- cards, own-goal and other negative-event expectation where modelled reliably

## Pinnacle objective
Primary objective: maximise expected FPL points on ensemble mean `xp`, subject to legal FPL squad, budget, club and formation constraints. The initial squad is optimised over the planning horizon with Gameweek-level XI/captain decisions. Risk is evaluated separately through stochastic scenarios/CVaR and exact selection regret.

## Elite 10.0 secondary utility
Elite is a secondary decision utility, never a new xP forecast.

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

### Set pieces and penalties — 10%
Raw role signal:
- 60% penalty share
- 15% corner share
- 15% direct free-kick share
- 10% indirect free-kick share

This is blended 75/25 with the set-piece xP prior.

### Fixture — 10%
Position-relative rank of match-specific `xp_attack + xp_clean_sheet`. This reuses the transparent projection's fixture translation rather than inventing a second undocumented fixture forecast.

### Bonus + DEFCON — 5%
Equal blend of position-relative bonus/BPS prior and defensive-contribution xP.

### Value — 5%
Position-relative rank of `xp / price`. Value may resolve near-ties but cannot dominate primary selection.

## Lexicographic / epsilon-constraint Elite optimisation
For each scenario (unrestricted, Haaland, no-Haaland):
1. solve maximum raw Pinnacle xP;
2. set `raw_xp_floor = max_xp_objective * (1 - epsilon)`;
3. maximise Elite utility subject to the same legal constraints and `raw_xp_objective >= raw_xp_floor`;
4. default provisional `epsilon = 0.005` (0.5% maximum raw-EV regret);
5. lock the resulting 15-player squad and re-optimise XI, captain and vice on raw xP.

This is intentionally stronger than multiplying xP by an arbitrary utility modifier: it guarantees that Elite can only choose from genuinely near-optimal expected-points solutions.

## Ownership
Ownership/EO is not an input to the maximum-points objective. If an explicit rank-management mode is requested, ownership may be used as a documented tiebreak or separate game-theoretic layer. It must not lower the canonical point forecast merely to create a differential.

## Uncertainty simulation
Do not sample each player's xPts independently. Scenarios should preserve realistic correlation, including:
- team attacking/defensive shocks
- opponent shocks
- player persistence
- minutes/start uncertainty
- rotation/no-show states
- correlated clean-sheet and scoring outcomes

Compare candidate squads using expected value plus distributional evidence such as floor/ceiling, CVaR and decision persistence. Expected value remains primary unless a different explicit objective is chosen.

## Planning horizon
Use a rolling multi-Gameweek horizon (normally 6-8 GWs with decay). Re-solve after new information rather than committing to a static season-long path.

## News and manual evidence
Injury, team news, manager comments and transfer/tactical evidence enter as structured availability/minutes/role inputs. They are not substitutes for the statistical model and must be timestamped/verified where possible.

## Chips
Evaluate chips as scenario comparisons on the same xPts framework. Automation is allowed only after the opportunity-cost logic is calibrated; until then conservative/manual policy is acceptable.

## Required comparison
For every Elite candidate report:
- maximum raw-xP reference
- Elite-selected squad raw xP
- raw-xP regret and regret percentage
- captaincy difference
- major minutes/role risks
- Haaland/no-Haaland differences
- stochastic robustness where material

## Promotion standard
Do not change weights, epsilon, fixture experts or player-rate allocation because a preferred player is missing. Changes require a benchmark hypothesis, no-hindsight evaluation where possible, and a recorded decision in `APEX_DECISIONS.md`.
