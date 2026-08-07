# Apex Pinnacle audit

**Audit date:** 7 August 2026

## Executive conclusion

The current Apex stack is a strong production-grade FPL decision engine, but a strict "pinnacle" standard should not stop at a deterministic mean/risk-adjusted xP optimiser.

The audit found one material structural weakness in the initial-squad path: the legacy MILP chooses a single GW1 XI/captain and gives every squad member a fixed fraction of aggregate horizon xP. That can prefer a large GW1 spike even when another player is clearly superior once future XI rotation is modelled explicitly.

A new `optimise_initial_horizon` solver has therefore been added. It fixes the 15-player squad while optimising a legal XI and captain independently for every Gameweek in the planning horizon. Adversarial regression tests demonstrate the case where the old heuristic and the full-horizon solution diverge.

## What is already strong

- Official FPL is canonical for identity, club, position, price, availability and fixtures.
- FPL Core and genuine pinned AIrsenal are independent enrichment/forecast workers.
- Expected minutes, tactical role, set pieces, xG/xA/xGI, fixture strength, 2026/27 bonus/BPS and defensive contributions are modelled.
- Projection disagreement and uncertainty are visible.
- Legal squad and transfer MILPs enforce FPL constraints.
- Personal FPL entry 63984 can seed weekly transfer planning after each deadline.
- An independent open-fpl-solver parity check validates mathematical constraint consistency.
- Source freshness and production readiness gates prevent stale/incomplete results from being labelled full Apex.

## Stress-test findings

### P0 — initial-squad horizon optimisation

**Finding:** legacy initial optimisation uses an aggregate heuristic rather than a true multi-period XI/captain model.

**Risk:** GW1 spike players can be overvalued relative to assets with superior GW2+ rotation/captain utility.

**Action:** new multi-GW initial-horizon MILP added. It should become the production initial-squad solver after CI validation.

### P0 — stochastic uncertainty / covariance

**Finding:** current risk adjustment is player-by-player. It does not model covariance between FPL outcomes.

Examples:
- goalkeeper + defender clean-sheet points from the same club are positively correlated;
- attackers and opposing defenders are negatively correlated;
- multiple attackers from the same team share team-goal uncertainty;
- captaincy concentrates outcome variance.

**Pinnacle upgrade:** scenario-based optimisation with a covariance-aware Monte Carlo layer and a downside objective such as CVaR / expected regret. The deterministic optimum should remain the baseline, not be discarded.

### P0 — decision stability

A single optimal squad can be misleading when several solutions are within fractions of a point.

**Pinnacle upgrade:** repeatedly solve under calibrated projection perturbations and report:
- selection probability;
- captain probability;
- objective regret if a player is forced/banned;
- near-optimal solution frequency;
- sensitivity to expected-minutes changes;
- sensitivity to model weights.

This turns "Player X is selected" into "Player X appears in 91% of plausible optimal solutions".

### P1 — captain/vice fallback

Current xP contains appearance risk and vice-captain is selected sensibly, but the optimisation objective does not explicitly value the captain-no-show -> vice-captain fallback pair.

**Upgrade:** pairwise expected captaincy value on a restricted captain candidate set so the fallback probability is part of the optimisation rather than a post-processing choice.

### P1 — bench/autosub value

Current squad/transfer objectives use a conservative bench-value proxy. Exact FPL autosub value depends on bench order, multiple no-shows and legal formation after substitutions.

**Upgrade:** stochastic autosub simulation or scenario-based bench-order optimisation.

### P1 — future transfer recourse

The current multi-GW transfer MILP produces the best path conditional on today's projections. In reality future information arrives before future transfers.

**Upgrade:** receding-horizon control plus a two-stage/scenario-tree model. Near-term moves should be committed; later moves should be represented as contingent branches rather than falsely treated as certain today.

### P1 — price dynamics

Manager-specific selling prices are reconstructed, but future market price moves are intentionally not guessed inside the optimiser.

**Upgrade:** optional calibrated price-change probability model. It should influence timing only when the expected team-value benefit is worth more than the option value of waiting for information.

### P1 — market priors

Market odds are supported but optional. A pinnacle forecast should use bookmaker-implied team goals, clean-sheet probability and scoring probability when a licensed/reliable feed is configured.

This should be an independent expert, not allowed to overwrite official identity or raw event data.

### P2 — rank / ownership strategy

Pure expected-points maximisation is correct for building the strongest generic team. Later in the season, maximising overall-rank utility can differ because effective ownership and rank state change the utility of variance.

**Upgrade:** optional strategy mode only. It must never contaminate the default expected-points objective.

## Recommended final architecture

```text
Canonical data
  Official FPL
      |
Feature / evidence layer
  FPL Core + preseason + tactical/set-piece + news + market
      |
Independent forecasts
  Apex transparent model + AIrsenal + market
      |
Calibrated ensemble
  mean xP + distribution + covariance
      |
Scenario engine
  minutes/injury/team-goal/CS/returns uncertainty
      |
Optimisation stack
  deterministic MILP baseline
  + full-horizon initial MILP
  + transfer/chip receding-horizon MILP
  + stochastic CVaR/regret solver
      |
Robustness layer
  independent solver parity
  selection stability
  sensitivity / regret
      |
Decision gate
  source freshness + model coverage + mathematical validity
      |
ChatGPT / GitHub decision interface
```

## Interaction contract

The intended user interface remains ChatGPT rather than a bespoke application.

Typical questions:

- `Run Apex now and give me the strongest 15.`
- `Stress-test the Haaland and no-Haaland structures.`
- `What is my best transfer this week?`
- `Roll or transfer?`
- `Give me the best 3-GW and 5-GW strategies.`
- `Show me the picks that are mathematically fragile.`
- `Which players survive the uncertainty stress test?`
- `How much expected value do I lose if I force Player X?`
- `What needs to happen for Player Y to become optimal?`

For direct GitHub use, the production workflows are manually dispatchable under the repository Actions tab. The compact published snapshot is the preferred durable interface for ChatGPT once a green publish has completed.

## Definition of "pinnacle"

Apex should only use that label when all of the following are true:

1. data and player identity are current and internally consistent;
2. independent projection workers are fresh and coverage-gated;
3. expected minutes and tactical assumptions are explicit;
4. legal optimisation is solved over the relevant horizon;
5. the chosen team is stable across plausible projection uncertainty, or instability is disclosed;
6. independent solver parity passes;
7. no important late injury/transfer/manager evidence is unresolved;
8. the user can see the expected-value gap and uncertainty rather than receiving a blind pick.
