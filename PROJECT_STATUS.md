# Apex FPL project status

**Status date:** 7 August 2026

## Current state

The repository has a production-green Apex core and a new **Apex Pinnacle** decision layer now being bootstrapped and stress-tested.

Validated core capabilities:

- Official FPL API is canonical for player ID, club, FPL position, price, availability and fixtures.
- Immutable Official FPL snapshot manifests and SHA256 checksums are recorded.
- FPL Core Insights enriches current player statistics, preseason data, Elo fixture context and defensive-contribution features.
- FPL Core data is resolved to an immutable current commit and refreshed automatically.
- Genuine pinned AIrsenal GW1–GW8 forecasts are exported through official `player.fpl_api_id`, provenance checked and freshness gated.
- Expected-minutes modelling produces start, appearance, 60+, 80+, expected-minutes and confidence estimates.
- Tactical roles, penalties, corners and free-kick shares support statistical inference plus verified overrides.
- Fixture difficulty combines Official FPL team strength, home/away context and reconciled FPL Core Elo.
- Transparent xP covers appearance, xG/xA attack, clean sheets, defensive contributions, saves, 2026/27 bonus/BPS potential and set pieces.
- The ensemble exposes model disagreement, uncertainty, floors/ceilings and risk-adjusted xP.
- Personal FPL entry **63984** is configured for post-deadline squad, bank, transfer/chip history and free-transfer synchronisation.
- Manager-specific selling prices are reconstructed from transfer history plus a pre-GW1 official price baseline.
- Multi-GW transfer optimisation supports 1–5 free transfers, hits, bank, XI, captain/vice and fixed Wildcard/Bench Boost/Triple Captain planning.
- Trusted news evidence is classified for injury/availability, transfers and manager/line-up risk without changing official identity.
- Independent pinned `open-fpl-solver` parity validates mathematical constraint consistency on identical projections.

## Stress-test findings and upgrades

The 7 August pinnacle audit found two material issues in the previous design and both have been addressed in code:

1. **Initial-squad horizon heuristic:** the legacy initial MILP used GW1 XI/captain plus a fixed fraction of aggregate horizon xP. An adversarial case can make this prefer a GW1 spike over a clearly superior multi-GW rotation asset. A new `optimise_initial_horizon` MILP fixes the 15-player squad while optimising a legal XI and captain separately for every Gameweek in the horizon.
2. **Pre-GW1 selling-price baseline:** the original public-entry flow returned before persisting the initial price universe when no public GW1 picks existed. That would make later selling prices for original GW1 players partly approximate. The price universe is now captured before the first deadline even while entry 63984 remains in initial-squad mode.

The new Pinnacle layer also adds exact **force/ban objective-regret analysis**. This quantifies how much expected objective value is lost when a selected player is removed or an alternative is forced, separating robust picks from near-ties.

New adversarial regression tests cover these cases.

## Pinnacle interface

Once the bootstrap workflow completes successfully, ChatGPT should prefer:

- `data/generated/pinnacle_latest.json`
- `data/generated/pinnacle_latest.md`

The existing validated core interface remains:

- `data/generated/apex_latest.json`
- `data/generated/apex_latest.md`
- `data/generated/solver_parity.json`
- `data/generated/airsenal.csv`
- `upstreams.lock.json`

Do not claim a current Pinnacle recommendation if `pinnacle_latest.json` is absent or stale. Fall back to the latest green Apex snapshot and state the limitation.

## Automation

Current workers include:

- FPL Core pin refresh — every six hours;
- normal full Apex publish — every six hours;
- **Apex Pinnacle** full-horizon/stress run — every six hours and manually dispatchable;
- genuine AIrsenal refresh inside production runs;
- independent solver parity on its validation cadence;
- dedicated final pre-GW1 recommendation on 21 August 2026 morning.

## Remaining mathematical upgrades before the theoretical ceiling

The deterministic Pinnacle layer is materially stronger, but a strict theoretical pinnacle still benefits from:

1. covariance-aware scenario simulation for correlated player/team outcomes;
2. stochastic optimisation using downside CVaR / expected regret;
3. explicit captain-no-show -> vice-captain fallback value;
4. stochastic bench/autosub ordering;
5. two-stage/receding-horizon transfer recourse for future information;
6. a calibrated future price-change timing model;
7. configured market-implied goal / clean-sheet / scorer priors from a reliable odds feed.

These should be added only with transparent calibration and backtesting rather than arbitrary complexity.

## Resume rule

For a future recommendation:

1. read `data/generated/pinnacle_latest.json` first;
2. require `safe_to_act=true` and `full_apex_ready=true`;
3. if unavailable, inspect the latest green `apex_latest.json` and disclose that the Pinnacle layer is not yet published;
4. never reconstruct a team from conversation memory when repository decision files are available.
