# Apex Pinnacle audit

**Audit date:** 7 August 2026

## Executive conclusion

The core Apex architecture is correct: official FPL truth -> statistical enrichment -> independent forecasts -> uncertainty -> legal optimisation -> robustness checks -> decision gate. Replacing that architecture with a different app or a single opaque AI model would make the system weaker, not stronger.

The stress audit did, however, find weaknesses that matter if the target is the mathematical pinnacle rather than merely a strong FPL optimiser. The most important ones have now been addressed in dedicated Pinnacle code rather than hidden behind confidence language.

## What is already strong

- Official FPL is canonical for identity, club, position, price, availability and fixtures.
- FPL Core and genuine pinned AIrsenal are independent enrichment/forecast workers.
- Expected minutes, tactical role, set pieces, xG/xA/xGI, fixture strength, 2026/27 bonus/BPS and defensive contributions are modelled.
- Projection disagreement and uncertainty are visible.
- Legal squad and transfer MILPs enforce FPL constraints.
- Personal FPL entry 63984 can seed weekly transfer planning after each deadline.
- Manager-specific selling values are reconstructed from public transfer history plus a pre-GW1 official price baseline.
- An independent open-fpl-solver parity check validates mathematical constraint consistency.
- Source freshness and production readiness gates prevent stale/incomplete results from being labelled full Apex.

## Stress-test findings and implemented upgrades

### P0 — true initial-squad horizon optimisation — IMPLEMENTED

**Finding:** the legacy initial MILP selected one GW1 XI/captain and gave every squad player a fixed fraction of aggregate horizon xP. An adversarial example can therefore overvalue a one-week spike over a clearly superior rotation asset.

**Upgrade:** `optimise_initial_horizon` fixes the 15-player squad but optimises a legal XI and captain independently in every Gameweek of the horizon. Adversarial regression tests explicitly demonstrate a case where this changes the correct decision.

### P0 — stochastic uncertainty / covariance — IMPLEMENTED AS ROBUSTNESS LAYER

**Finding:** the original risk adjustment was player-by-player and therefore treated important shared uncertainties as independent.

The new scenario layer generates correlated forecast surfaces with:
- shared club attack shocks;
- shared club defensive shocks;
- common Gameweek shocks;
- negative attacker-vs-opposing-clean-sheet linkage;
- remaining idiosyncratic projection uncertainty;
- marginal volatility anchored to the existing projection SD.

The new stochastic MILP then maximises a blend of mean horizon value and lower-tail **Conditional Value at Risk (CVaR)**. A single squad/XI/captain decision is used across every scenario for each Gameweek, preventing impossible scenario-by-scenario perfect foresight.

This layer is intentionally a *robustness stress model*. Its covariance coefficients are transparent priors and are **not yet claimed to be walk-forward calibrated 2026/27 parameters**. The deterministic full-horizon optimum remains the expected-value baseline; agreement with the CVaR solution materially raises decision confidence, while disagreement is surfaced.

### P0 — decision stability — PARTIALLY IMPLEMENTED

A single optimum can conceal a near-tie. Apex now performs exact force/ban re-solves:
- ban each selected player and measure lost objective value;
- force the strongest unselected alternatives and measure regret;
- expose structurally robust picks vs choices that are only fractions of a point apart.

The next extension is repeated solve-frequency under calibrated forecast perturbations to produce empirical selection/captain probabilities.

### P0 — pre-GW1 selling-price state — FIXED

The audit found that the original public-entry flow could return before persisting the pre-GW1 price universe because no public picks exist before the first deadline. That would later make some original-player selling prices approximate.

The initial price universe is now captured before GW1 even while entry 63984 remains in initial-squad mode, with a regression test covering the failure mode.

## Remaining improvements before the theoretical ceiling

### P1 — captain/vice fallback

Current projections include appearance risk and vice-captain selection is availability-aware, but the captain objective still does not explicitly price the probability that the captain misses out and the vice inherits the multiplier.

**Upgrade:** pairwise captain/vice expected value inside the stochastic decision layer.

### P1 — exact bench/autosub value

The initial and transfer solvers use a conservative bench-value proxy. Exact FPL value depends on bench order, multiple no-shows and legal formation after automatic substitutions.

**Upgrade:** scenario-based autosub and bench-order optimisation.

### P1 — future transfer recourse

The transfer MILP gives the best path conditional on today's information. Real managers receive new information before future moves.

**Upgrade:** receding-horizon control / two-stage scenario tree. Commit the immediate move while treating later transfers as contingent rather than falsely certain.

### P1 — price timing

Exact current selling value is modelled; future price changes are intentionally not guessed.

**Upgrade:** optional calibrated price-move probabilities used only when the expected team-value gain exceeds the option value of waiting for news.

### P1 — market priors

Odds support exists but is optional. A stronger independent expert would use reliable market-implied team goals, clean-sheet probability and scorer probabilities.

Market data must remain an expert layer and never overwrite official identity/statistical truth.

### P2 — rank / ownership strategy

Pure expected-points maximisation is the correct default for the strongest team. Later in a season, rank utility can justify different variance.

**Upgrade:** optional rank/effective-ownership strategy mode only; it must not contaminate the default expected-points engine.

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
  mean xP + uncertainty
      |
Correlated scenario engine
  team attack/defence + opponent linkage + idiosyncratic uncertainty
      |
Optimisation stack
  deterministic full-horizon MILP
  + covariance-aware mean/CVaR MILP
  + transfer/chip receding-horizon MILP
      |
Robustness layer
  exact force/ban regret
  + independent solver parity
  + future solve-frequency calibration
      |
Decision gate
  source freshness + model coverage + mathematical validity
      |
ChatGPT / GitHub decision interface
```

## Interaction contract

The intended user interface remains ChatGPT rather than a bespoke application. Useful requests include:

- `Run Pinnacle now and give me the strongest 15.`
- `Stress-test the Haaland and no-Haaland structures.`
- `Do the deterministic and CVaR teams agree?`
- `Which picks are mathematically fragile?`
- `What is my best transfer this week?`
- `Roll or transfer?`
- `Give me the best 3-GW and 5-GW strategies.`
- `How much expected value do I lose if I force Player X?`
- `What needs to happen for Player Y to become optimal?`

For direct GitHub use, **Actions -> Apex Pinnacle -> Run workflow** manually executes the full stress path. Once the green workflow publishes, `data/generated/pinnacle_latest.json` is the durable ChatGPT decision interface.

## Definition of "pinnacle"

Apex should use the label only when:

1. data and identity are current and internally consistent;
2. independent projection workers are fresh and coverage-gated;
3. expected-minutes/tactical assumptions are explicit;
4. the legal squad is solved over the relevant horizon;
5. deterministic and stochastic robustness evidence is available and any disagreement is disclosed;
6. exact selection-regret sensitivity is available;
7. independent solver parity passes;
8. no important late injury/transfer/manager evidence is unresolved;
9. expected-value gaps, downside and uncertainty are visible rather than hidden behind a single score.

The covariance stress layer is now implemented, but its coefficients remain transparent priors until enough deadline/outcome history exists for walk-forward calibration. That limitation should be stated rather than disguised as certainty.
