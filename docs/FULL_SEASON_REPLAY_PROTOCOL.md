# Apex FPL — Full-Season Replay Protocol

## Purpose

The replay is a deterministic, deadline-by-deadline test of the complete Apex
manager: forecasts, initial squad, transfers, hits, chips, XI, bench order,
captaincy, autosubs and state transitions.  A final points total alone is not a
valid test unless every decision was made from information available before that
deadline.

## Validation status of seasons

- **2025/26 is a locked pseudo-prospective integration benchmark.** PR #14 and
  PR #16 development inspected evidence from that completed season, so it is no
  longer an independent model holdout.
- **2026/27 is the prospective validation season.** Freeze code, configuration,
  policies and metrics before outcomes are available, then preserve every
  pre-deadline decision.

No report may describe the 2025/26 replay as blind or untouched.

## Information cutoff

The canonical cutoff is `deadline - 120 minutes`.

Every source manifest entry must contain:

- source name and immutable revision;
- `published_at`, `available_at` and `retrieved_at` in UTC;
- content SHA-256;
- source reference/URL where applicable.

Any source with `available_at > cutoff` is a hard failure.  The decision process
must not mount outcome data and should run without network access after the input
bundle is sealed.

## Weekly input bundle

Each Gameweek bundle contains:

- `AsOfContext` and its manifest hash;
- Official FPL identity, position, club, price, availability and fixtures as of
  the cutoff;
- the latest FPL Core revision available before the cutoff;
- Understat matches completed before the cutoff only;
- pinned AIrsenal state rebuilt from information available before the cutoff;
- timestamped official/credible news available before the cutoff;
- the previous permanent team state and decision hash;
- frozen model/configuration/runtime identifiers.

Outcome files are stored separately and become visible only to the scorer after
the decision artifact has been sealed.

## State machine

The replay must carry forward:

- permanent 15-player squad;
- temporary Free Hit squad where applicable;
- bank and purchase-price ledger;
- free-transfer balance;
- chip inventory by half-season;
- XI, ordered bench, captain and vice-captain;
- previous state and decision hashes.

Season-specific rules come from `apex_fpl.rules.SeasonRules`.  For 2025/26 this
includes the GW16 AFCON top-up to five free transfers.  Before GW1 the manager has
unlimited squad changes but zero bankable free transfers; after the GW1 deadline
one free transfer is available for GW2.

## Decision contract

One `WeeklyAction` is sealed per Gameweek:

- transfers in/out and hit;
- chip or explicit hold;
- resulting permanent/temporary squad;
- legal XI and bench order;
- captain and vice-captain;
- resulting bank, FT ledger and state hash.

No manual choice may be made after viewing that Gameweek's results.  Missing
mandatory evidence produces a recorded safe-hold action and an operational test
failure; it must not be silently backfilled from later data.

## Realised scoring

The scorer uses official FPL event totals as truth and reproduces:

- blanks, doubles and postponed-fixture event assignment;
- legal autosubs and goalkeeper-only goalkeeper replacement;
- captain-to-vice inheritance only when the captain records zero minutes in the
  whole event;
- Triple Captain and Bench Boost;
- hit deductions exactly once;
- Free Hit reversion to the permanent squad, bank and purchase ledger.

Every contribution and state transition must reconcile to the season total.

## Benchmarks

All policies receive identical sealed bundles and rules:

1. canonical Apex ensemble;
2. Official-FPL xP only;
3. genuine pinned AIrsenal only;
4. Apex transparent model only;
5. one-GW greedy transfer policy;
6. GW1 buy-and-hold with weekly XI/captain optimisation;
7. clairvoyant oracle as an unattainable diagnostic only.

## Mandatory gates

### Integrity

- 38/38 sealed decisions;
- zero rows available after the cutoff;
- zero target-GW outcomes visible to decision code;
- 100% legal squads, transfers, chips, XIs and benches;
- complete bank, FT, purchase-price and chip reconciliation;
- byte-identical repeated decisions from the same bundle/SHA/config;
- complete hash chain from GW1 through GW38.

### Forecasts

Against the strongest predeclared single expert, the upper 90% block-bootstrap
confidence bound for relative RMSE degradation must be no worse than +1%.
Appearance/start/60-minute and clean-sheet calibration must not materially worsen.

### Decisions

Primary metric: net season points versus the strongest predeclared automated
non-Apex policy.

- **Strong pass:** lower 90% paired block-bootstrap bound above zero.
- **Provisional pass:** positive realised delta and `P(delta > 0) >= 0.75`.
- **Fail:** non-positive mean delta or `P(delta > 0) < 0.50`.

Also report captain gain, transfer gain/regret, hit cost, chip gain, autosub points,
bench waste, forecast error and source failures.  A single season cannot establish
general superiority; changes made after inspecting 2025/26 must be judged on the
prospective 2026/27 archive.
