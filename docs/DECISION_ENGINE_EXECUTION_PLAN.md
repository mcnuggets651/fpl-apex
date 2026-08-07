# Apex decision-engine execution plan

**Status:** implementation contract

**Created:** 7 August 2026
**Primary objective:** maximise defensible expected FPL points while exposing, rather
than hiding, uncertainty in data, projections and decisions.

## Non-negotiable standard

A green workflow is not sufficient evidence that a recommendation is trustworthy.
Production publication requires three separate gates:

1. **Data ready** — official identity and fixtures are current, critical feature
   groups meet their coverage contracts, mappings are unambiguous and missing
   observations have not been converted into measured zeroes.
2. **Model ready** — every production expert is versioned, its coverage is known,
   and any learned parameter or weight has out-of-sample evidence from a genuinely
   point-in-time evaluation.
3. **Decision ready** — the legal optimiser, exact captain/vice/autosub mechanics,
   sensitivity analysis and late-news checks all pass. Unsupported outliers may not
   be labelled safe to act on.

`safe_to_act=true` requires all three. Operational success remains visible
separately and must never imply analytical confidence.

## Architecture

```text
Official FPL identity, prices, rules and fixtures
  -> field-level data-quality contracts

Understat xG + Elo + market evidence
  -> leakage-safe team attack/defence model
  -> fixture goal and clean-sheet distributions

Historical player returns + preseason + news
  -> expected-minutes and role distributions
  -> player goal/assist/clean-sheet/bonus components
  -> transparent Apex expected-points forecast

Apex + genuine AIrsenal + official forecast + market forecast
  -> walk-forward calibrated ensemble
  -> correlated projection scenarios
  -> squad/XI/captain/bench/transfer/chip optimisation
  -> selection frequency, regret and fallback analysis
  -> strict decision packet
```

Official FPL remains canonical for player identity, club, FPL position, price,
availability, scoring rules and future fixtures. External sources may enrich or
forecast those entities but may not overwrite them.

## Capability audit after the Betting Predictor handoff

| Capability | Current state | Production meaning | Next evidence required |
|---|---|---|---|
| Official FPL identity, price, position, fixtures | Production | Canonical and freshness/hash gated | Continue live adapter smoke tests |
| Field-level data quality | Production in this change | Missing, zero and invalid surfaces can block publication | Add deadline fixtures for every upstream schema |
| Direct cached Understat history | Shadow challenger | Five complete seasons validated; active season optional | Keep cache/coverage evidence in every research run |
| Team-name mapping and promoted priors | Shadow challenger | Controlled aliases; unknown/promoted clubs receive league priors | Publish unmatched-team report and validate promoted cohorts |
| Understat team-goal model | Shadow challenger | Beats the league baseline over 1,140 held-out matches but is not promoted | Gameweek-block bootstrap, decision-regret and source-removal gates |
| Official-strength/Elo fixture model | Production champion | Invalid zero strengths fall back to neutral goals plus complete reconciled Elo | Benchmark against the eventual promoted xG model and market |
| Prior-season player minutes bridge | Production prior | Stable player code maps prior starts/minutes to current official IDs | Deadline-level Brier/calibration/minutes-MAE evaluation |
| Preseason evidence | Production with missingness controls | Unobserved returns remain missing rather than measured zero | Learn weights by cohort through ablation |
| AIrsenal | Production required expert | Genuine IDs, full requested horizon, plausible numeric surface and 95% player coverage | Historical deadline archive and source ablation |
| Market forecast | Optional, not maximum-confidence | Adapter exists; absence does not pretend to be market confirmation | Reliable de-vigged team/scorer feed and freshness contract |
| Ensemble weights | Production priors, not calibrated claim | Transparent fixed weights are renormalised across healthy experts | Walk-forward non-negative regularised calibration |
| Legal initial/transfer optimiser | Production | Full horizon, exact constraints, FT/hit/bank handling and independent parity | Historical decision-value replay |
| Captain, vice, autosub and bench | Production decision mechanics | No-show fallback and legal appearance-state mechanics are explicit | Prospective calibration of appearance probabilities |
| Decision stability | Production audit | Force/ban regret plus correlated-scenario squad/XI/captain frequencies | Calibrate scenario covariance from archived deadlines |
| GW1-GW5 route | Production policy | Only GW1 is executable; GW2-GW5 moves are stored contingencies | Refresh and re-solve before every deadline |
| Chips | Conservative hold policy | Immediate-window value cannot spend a chip automatically | Remaining-half opportunity-cost distribution |
| Full historical FPL shadow replay | Partial | Prospective archive is genuine; complete historical deadline store is not yet proven | Immutable point-in-time player/Gameweek feature store |

The direct Understat client, strict validation, atomic cache, canonical mapping,
promoted-team prior and chronological evaluation patterns are the reusable parts of
the Betting Predictor. Its 1X2 targets, staking, Kelly, fair-odds and CLV policies
remain outside Apex because they do not solve player-points or FPL squad decisions.

## Champion/challenger rule

Every material model change is introduced as a shadow challenger.

- The current production model remains reproducible and versioned.
- Training, tuning and final evaluation use different chronological data.
- Promotion occurs in a separate pull request after evidence is published.
- No feature receives weight because it is intuitively attractive.
- If a simple benchmark beats the challenger, the benchmark remains champion.
- Rollback is a configuration/model-version change, not a code archaeology task.

## Work packages

### A0 — Baseline and regression contract

- Preserve a compact fixture representing the latest production decision.
- Add regressions for unsupported captaincy, invalid official team-strength fields,
  missing preseason observations, expert disagreement and horizon coverage.
- Record model version, configuration, source versions and input hashes in every
  decision artifact.

### A1 — Field-level data quality

- Validate official identity, fixtures and team-strength fields independently.
- Validate FPL Core player, preseason-stat and Elo coverage independently.
- Validate AIrsenal horizon, IDs, freshness, provenance and numeric distributions.
- Preserve `missing`, `observed_zero` and `observed_value` as distinct states.
- Require complete critical coverage for every final decision candidate.

### A2 — Resilient football data layer

- Adapt the Betting Predictor Understat client: compressed responses, bounded
  retry, validation before caching, atomic writes and useful root-cause errors.
- Keep completed-season caches immutable; refresh the active season.
- Permit validated stale cache only in research mode and only within a declared
  source-specific limit. A deadline decision cannot silently use stale critical
  evidence.
- Near season end, shorten to real official future Gameweeks; never fabricate a
  fixture window.

### A3 — Canonical team, player and fixture mapping

- Team key: season plus official FPL team ID.
- Player key: season plus official FPL player ID.
- Fixture key: official fixture ID, with mapped-team/date reconciliation only for
  external historical sources.
- Report every unmatched or ambiguous mapping. Critical live ambiguity is fatal.

### A4 — No-hindsight historical feature store

- Materialise immutable player/Gameweek rows from data available before each
  historical deadline.
- Assert every feature timestamp is earlier than its deadline.
- Store expert forecasts, expected minutes, component xP and official outcomes.
- Version scoring rules. Older FPL totals cannot validate a new scoring component
  unless the component can be reconstructed honestly.
- Replay at least three seasons before claiming historical decision evidence.

### A5 — Team expected-goals model

- Estimate time-decayed home/away attack and defence from xG/npxG history.
- Produce expected goals for both teams and clean-sheet probabilities for every
  official future fixture.
- Use a hierarchical historical promoted-team prior at season boundaries.
- Benchmark against league averages, valid official strength, Elo and market
  estimates. Poisson/Dixon-Coles is an intermediate distribution, not player xP.

### A6 — Expected-minutes model

- Model start, appearance, 60-plus and conditional minutes separately.
- Use prior minutes, recent selection, squad competition, preseason, availability,
  transfers, congestion and verified news.
- Learn preseason weight through ablation; do not use a fixed intuitive weight as
  a permanent production parameter.
- Evaluate Brier score, calibration and minutes MAE by position and player cohort.

### A7 — Team-consistent player projections

- Allocate team attacking expectation among likely players using minutes, role,
  non-penalty xG, penalties, assist shares and shrinkage priors.
- Reconcile player attacking totals to the team environment.
- Add appearance, clean sheets, saves, defensive contributions, set pieces and
  bonus as auditable components without double-counting.
- Handle blanks and Double Gameweeks explicitly.

### A8 — Market expert

- Convert team-goal, clean-sheet and scorer prices into de-vigged probabilities.
- Aggregate reliable books and enforce mapping, freshness and coverage contracts.
- Market evidence is an independent expert and benchmark, never identity truth.
- Highest confidence is unavailable when a required market check is absent.

### A9 — Walk-forward ensemble

- Fit non-negative regularised weights only to out-of-fold deadline forecasts.
- Start with a global weight vector. Add position/horizon/season-phase variation
  only after effective sample size supports it.
- Bootstrap by Gameweek because player outcomes within one Gameweek are correlated.
- Bound influence from experts without genuine historical deadline archives.
- Do not auto-promote a calibration from one Gameweek.

### A10 — Decision policy

- Put exact captain/vice fallback and autosub value inside the objective.
- Sample uncertainty in minutes, team goals, player rates and expert weights.
- Publish squad, XI and captain selection frequencies plus force/ban regret.
- Commit only the immediate transfer; future actions remain scenario-contingent.
- Value free transfers, bank and flexible price structures as options.
- Judge chips against remaining-season opportunity cost, not only the next window.

### A11 — Production decision packet

The durable artifact contains the 15, XI, bench order, captain, vice, GW1 and
multi-GW projections, component drivers, expected minutes, source forecasts,
uncertainty, selection frequency, alternatives, price-saving routes, transfer
triggers, chip policy, source timestamps and expiry time.

For every material omission it must answer: what change in minutes, team goal or
clean-sheet expectation would make that player optimal?

## Evaluation and promotion metrics

Forecast evaluation includes MAE, RMSE, bias, rank correlation, interval coverage
and component-appropriate Brier/log scores. Decision evaluation includes realised
points, captain regret, selection regret, transfer-hit value and performance against
simple legal-squad and incumbent baselines.

Promotion requires:

- all leakage and coverage checks pass;
- improvement is out-of-sample and consistent across chronological folds;
- a Gameweek-block bootstrap supports the improvement;
- decision regret does not materially deteriorate;
- weights and choices are stable to removing any one optional source;
- the evidence artifact and model version are committed before production weights
  change.

## Season-boundary and fixture-window rules

- Before current-season matches exist, carry prior-season posteriors forward with
  greater uncertainty.
- Promoted teams use a leakage-safe hierarchical prior.
- Active-season corrections refresh the cache and update checksums.
- Rescheduled, postponed, blank and Double Gameweek fixtures use official FPL state.
- If fewer future actionable Gameweeks exist than requested, the horizon is clipped
  and disclosed. Missing Gameweeks are never fabricated.

## Delivery order for the final GW1 decision

1. Block the current false-green cases.
2. Establish resilient data, canonical mappings and no-hindsight evaluation.
3. Promote only validated team-goal, minutes and player-projection challengers.
4. Bound unvalidated ensemble experts and add market evidence when reliable.
5. Generate decision frequencies, fallbacks and transfer-route sensitivity.
6. Run repeated shadow decisions before the final deadline refresh.
7. On deadline day refresh official data, verified news, market evidence and
   AIrsenal, then publish only if all three gates pass.

Current-season calibration starts from genuine archived pre-deadline forecasts.
Until that evidence exists, the artifact must label priors as priors and lower its
confidence rather than manufacture certainty.

## Small pull-request sequence after this foundation

1. **Point-in-time feature store:** reconstruct immutable player/Gameweek inputs,
   enforce `feature_timestamp < deadline`, and replay three complete seasons.
2. **Minutes challenger:** evaluate start/appearance/60-plus calibration and minutes
   MAE by position, prior evidence and preseason cohort; promote weights separately.
3. **Team-goal promotion audit:** add Gameweek-block bootstrap, decision-regret and
   leave-one-source-out evidence; only then change `understat_team_model_mode`.
4. **Player component reconciliation:** constrain player goal/assist shares to the
   team goal surface and verify no double counting by player, club and Gameweek.
5. **Expert ablation and ensemble:** archive official, Apex, AIrsenal and market
   deadline forecasts; compare each expert and fit regularised non-negative weights.
6. **Chip opportunity cost:** replay legal remaining-half chip schedules and publish
   a recommendation only when the current advantage clears the calibrated future
   distribution.
7. **Deadline production run:** refresh all required sources, run repeated scenario
   solves and alternatives, publish the final 15 and GW1 mechanics only if every
   strict gate remains green.

Each PR must include its evidence artifact, rollback switch, coverage regression and
no-hindsight test. Code completion alone is not a promotion event.
