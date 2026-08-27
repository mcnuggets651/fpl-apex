# Apex FPL project status

**Status date:** 27 August 2026

## V2 control-plane status — 27 August 2026

Apex V2 is in a stacked engineering-certification migration, not live production cutover. PRs #75–#86 remain the preceding unmerged V2 stack; #86 is engineering-certified but production is WITHHELD. PR #87 adds explicit champion selection authority so a qualified candidate or mutable registry/configuration row cannot become production authority by implication.

#87 now binds production publication and answer authority to one immutable point-in-time `ProductionChampionGeneration`. Forecast champion authority must be independently re-derived from exact retained learning evaluation/comparison/policy evidence; DecisionPolicy, scenario-generator and scenario-policy champions require separate reviewed admissions with typed empirical qualifications. The exact generation must match the schema-v2 production planning bundle and is retained in schema-v2 `ProductionPublicationAuthorization`. Synthetic fixtures prove mechanism only.

No real 2026/27 forecast champion, DecisionPolicy champion, scenario champion, planning reference-solver champion, deployed production PostgreSQL Plane-B evidence, prospective future qualification outcome or PUBLISHED V2 release is asserted. Until those genuine authorities exist and the full cutover chain passes, `ready_to_act` and `safe_to_act` remain false for V2 production.

## Current state

The repository has a production-green Apex core and an enhanced **Apex Pinnacle** decision layer now being bootstrapped and stress-tested.

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

The 7 August pinnacle audit found material weaknesses in the previous decision layer and they have been addressed in new code:

1. **Initial-squad horizon heuristic:** the legacy initial MILP used GW1 XI/captain plus a fixed fraction of aggregate horizon xP. An adversarial case can make this prefer a GW1 spike over a clearly superior multi-GW rotation asset. `optimise_initial_horizon` now fixes the 15-player squad while optimising a legal XI and captain separately for every Gameweek.
2. **Independent-player risk assumption:** the original risk adjustment did not model shared team/opponent uncertainty. The Pinnacle scenario generator now creates correlated forecast surfaces and a new MILP maximises a blend of mean value and lower-tail **CVaR**.
3. **Pre-GW1 selling-price baseline:** the original public-entry flow could return before persisting the initial price universe when no public GW1 picks existed. The price universe is now captured before the first deadline even while entry 63984 remains in initial-squad mode.
4. **Near-tie visibility:** exact force/ban objective-regret analysis now quantifies how much value is lost when selected players are removed or alternatives are forced.

The stochastic layer models common Gameweek shocks, shared team attack/defence uncertainty and negative attacker-vs-opposing-clean-sheet linkage. Its covariance coefficients are transparent priors and are not yet claimed to be walk-forward calibrated 2026/27 parameters. It is therefore used as robustness evidence alongside the deterministic expected-value optimum, not as a magic replacement for it.

Adversarial regression tests cover the full-horizon and CVaR failure modes.

## Pinnacle interface

Once the bootstrap workflow completes successfully, ChatGPT should prefer:

- `data/generated/pinnacle_latest.json`
- `data/generated/pinnacle_latest.md`

The Pinnacle snapshot contains:

- deterministic full-horizon unrestricted / Haaland / no-Haaland solutions;
- covariance-aware CVaR versions of the same scenarios;
- deterministic-vs-robust overlap;
- exact selection-regret sensitivity;
- scenario downside/median/upside summaries;
- current personalised transfer plan when the public team is available;
- source and official-snapshot provenance.

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
- **Apex Pinnacle** full-horizon + correlated 256-scenario CVaR stress run — every six hours and manually dispatchable;
- genuine AIrsenal refresh inside production runs;
- independent solver parity on its validation cadence;
- dedicated final pre-GW1 recommendation on 21 August 2026 morning.

## Remaining mathematical upgrades before the theoretical ceiling

The strongest remaining improvements are now narrower:

1. walk-forward calibration of the scenario covariance coefficients and stochastic risk weight;
2. explicit captain-no-show -> vice-captain fallback value inside the objective;
3. stochastic bench/autosub ordering and formation-safe substitutions;
4. two-stage/receding-horizon transfer recourse for future information;
5. a calibrated future price-change timing model;
6. configured market-implied goal / clean-sheet / scorer priors from a reliable odds feed;
7. empirical selection/captain frequency across calibrated projection perturbations.

These should be added only with transparent calibration and backtesting rather than arbitrary complexity.

## Resume rule

For a future recommendation:

1. read `data/generated/pinnacle_latest.json` first;
2. require `safe_to_act=true` and `full_apex_ready=true`;
3. inspect deterministic-vs-CVaR agreement and selection regret before calling a pick high confidence;
4. if Pinnacle is unavailable, inspect the latest green `apex_latest.json` and disclose that the enhanced layer is not yet published;
5. never reconstruct a team from conversation memory when repository decision files are available.
