# Apex V2 External Shadow Provider Reliability

## Scope

This document defines the permanent reliability boundary for Dastan, PITCHSIDE and OpenFPL under the frozen Apex V2 engine SHA `99cc7b51b0cff45462b567084cb1844cfe0a456f`.

The serving architecture is unchanged:

- AIrsenal is the sole serving champion H1-H8.
- Dastan remains SHADOW and H1-only.
- Apex Proprietary remains SHADOW H1-H8.
- PITCHSIDE is a non-serving external forecast source.
- OpenFPL is a governed non-serving research source.
- no blending, voting or automatic promotion is permitted.
- provider-health and tournament records have `production_influence = NONE`.

The reliability layer exists so a challenger can fail visibly without either silently disappearing or making an otherwise valid production recommendation unactionable.

## September 1 incident reconstruction

Production run `33469824474-1` was independently actionable. AIrsenal served H1-H8 and Official parity passed.

The first interpretation of the degraded provider surface was partially wrong.

### Dastan

Dastan did **not** fail in the inspected production run. It was:

- `HEALTHY`;
- H1 `QUALIFIED`;
- `SHADOW`;
- `serve_authorized = false`.

The long-term weakness was operational, not predictive: every live attempt clones the pinned upstream and installs/runs the worker, so transient DNS/Git/package-index failures could unnecessarily remove the shadow from an otherwise healthy attempt.

### PITCHSIDE

The production qualification matrix reported an incomplete universe because the frozen production contract treated all Official identities as requiring a numerical forecast.

A deeper inspection of the first September 1 PITCHSIDE publication established the real shape of that snapshot:

- 626 current player identities in `players.json`;
- 575 player forecast vectors in `xp.json`;
- exactly 51 identities without forecast vectors;
- all 51 omitted identities were Official/PITCHSIDE `status = u`;
- every forecastable active/injured/doubtful/suspended identity had a target-GW forecast;
- the 575 forecast vectors covered GW3-GW19.

Therefore that source snapshot was not missing 51 legitimate decision-universe forecasts. The blanket 626/626 rule was the defect.

The correct accounting is:

- every Official identity is retained for audit;
- `status = u` identities are `NO_FORECAST_EXPECTED`;
- every other Official identity is forecastable and must contain a finite value at each horizon the source claims to support;
- a missing forecastable player is still a hard `INCOMPLETE_UNIVERSE` tournament DNS;
- no zero-fill, interpolation, AIrsenal backfill or postdeadline regeneration is allowed.

PITCHSIDE also publishes independently of Apex. Its `generated_utc` may legitimately predate the start of the Apex process. Freshness is therefore source age plus target-GW/predeadline validity, not `generated_at >= Apex attempt_started_at`.

### OpenFPL

The missing `acquisition/providers/openfpl.csv` was not a transient upstream outage.

The governed current-rules policy requires at least **10 completed 2026/27 exact-rule Gameweeks** before a current-rules derivative may be built. Legacy fitted weights cannot be reused under the changed scoring rules.

The previous frozen history pin could also become permanently stale: if readiness only reads a fixed commit, it never notices new season Gameweeks.

The operations repair resolves the configured current-season history branch to an exact immutable commit on every readiness check, inventories only `gwN.csv` files, intersects them with Official events marked both `finished=true` and `data_checked=true`, and records the immutable commit plus manifest hash.

The health/readiness and tournament states deliberately answer different questions:

- `TRAINING_NOT_READY`: fewer than 10 legitimate exact-rule completed Gameweeks exist;
- `READY_FOR_SHADOW_BUILD`: the readiness monitor has proved the history floor is satisfied and a governed shadow build is permitted;
- `TRAINING_READY_NO_MODEL`: the tournament layer's state when the history floor is satisfied but no separately validated current-rules model/export has been sealed;
- `ENTERED`: only after a legitimate predeadline OpenFPL forecast surface actually exists and passes tournament qualification.

This distinction prevents the 10-GW threshold from being mistaken for a usable model.

The pinned OpenFPL method repository exposes a notebook/sample-data method, not a validated reproducible current-rules production exporter. Apex therefore does not invent one. Until such a builder is separately validated, crossing the floor is visible as `TRAINING_READY_NO_MODEL`, never a synthetic forecast.

## Live post-merge acceptance proof — 2026-09-01 22:13 UTC

The read-only `Apex V2 External Shadow Health` workflow ran automatically from merged operations SHA `fc2d9af77bd0da9b94fdbc4fea3257a32668a72c` and completed successfully. It exercised the real upstreams without manager credentials, solving or production publication.

The resulting states were:

- **Dastan:** `HEALTHY / PIN_REACHABLE`; pinned and observed commit both `19376523afdec4836d0e6b5632c6773d0fe40c53`.
- **OpenFPL:** `HEALTHY / TRAINING_NOT_READY`; 1 governed exact-rule Gameweek available of the required 10; observed history commit `9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88`.
- **PITCHSIDE:** `INCOMPLETE`; the Official universe had grown to 629 identities, 568 of which were forecastable under `status != u`, while the current PITCHSIDE publication had forecasts for 565 of those 568. Exact missing Official element IDs were `627`, `628`, and `629`, with player codes `155465`, `482616`, and `624777`.

This later PITCHSIDE result does **not** contradict the earlier 575/575 forecastable snapshot. It demonstrates why the health contract must be dynamic: Official FPL added three forecastable identities after that earlier publication. The monitor correctly moved PITCHSIDE from complete to `INCOMPLETE` instead of freezing an obsolete universe or inventing forecasts. Until the external source publishes those identities, tournament treatment is explicit DNS/`INCOMPLETE_UNIVERSE`; no substitute values are permitted.

The live artifact was retained as `apex-v2-external-shadow-health-33565153740` (artifact id `9822817588`).

## Permanent provider contracts

### Dastan resilience

Dastan remains an attempt-local H1 shadow. The operations wrapper now provides:

1. exact frozen upstream-pin health preflight;
2. bounded acquisition retry;
3. retry only for recognized transient network/package-index failures;
4. no retry for Official-hash mismatch, schema/model errors or invariant failures;
5. bounded wall-clock budget;
6. sanitized failure excerpts and hashed raw process output;
7. explicit attempt count and failure class;
8. no serving authority or fallback forecast.

The successful Sep 1 Dastan result remains valid evidence; the retry policy is preventive hardening rather than a reinterpretation of that run.

### PITCHSIDE health and tournament capture

The read-only health monitor and prospective tournament capture both enforce:

1. Official public bootstrap/fixture anchoring;
2. bounded retry only for transient HTTP/network errors;
3. double-read of `meta.json` to reject mid-download deployment changes;
4. SHA-256 identity for every upstream object;
5. exact target Gameweek from Official FPL;
6. exact `player_code -> Official fpl_code -> element_id` identity mapping;
7. target GW must exist in the xP matrix;
8. source generation must precede the Official target deadline;
9. source must satisfy the governed freshness window;
10. every forecastable Official identity must have a finite forecast at each claimed horizon;
11. `status = u` identities remain explicitly accounted for as `NO_FORECAST_EXPECTED`;
12. no fuzzy mapping or value fabrication;
13. atomic diagnostic output.

The health layer may classify the source `HEALTHY`, `INCOMPLETE`, `STALE` or `ERROR`. Tournament qualification independently converts the sealed source into `ENTERED` or an exact DNS reason.

### OpenFPL readiness

OpenFPL readiness records:

- pinned OpenFPL method repository and commit;
- frozen historical baseline identity;
- dynamically resolved current-season history commit;
- immutable history manifest hash;
- exact observed Gameweeks;
- Official-finished/data-checked intersection;
- governed 10-GW minimum;
- prohibition on legacy fitted-weight reuse;
- `auto_build = false`;
- `auto_promotion = false`;
- `serve_authorized = false`;
- `production_influence = NONE`.

A readiness failure is visible but cannot change production serving authority.

## Separation from production certification

PITCHSIDE and OpenFPL are removed from the frozen production qualification matrix by the derived runtime config because they are externally scheduled/research providers whose failure semantics differ from serving qualification.

This does **not** remove them from research accountability:

- PITCHSIDE is captured prospectively by the separate tournament controller against the exact Official production hash;
- OpenFPL is always represented by an explicit readiness/DNS state;
- every expected tournament provider must be either `ENTERED` or DNS;
- silent omission is forbidden.

Dastan and Apex Proprietary remain attempt-local SHADOW providers inside the frozen production snapshot. AIrsenal remains sole serving champion.

## Post-ops runtime acceptance

External shadow health is part of the repository's permanent post-ops acceptance pattern. In addition to manual dispatch and fixed schedules, `Apex V2 External Shadow Health` runs after a relevant push to `main` that changes its workflow or `scripts/apex_v2_shadow_provider_ops.py`.

That push path remains strictly read-only:

- `contents: read` only;
- no FPL manager credentials;
- no private-manager token;
- no solver;
- no production publish;
- no provider serving authority.

The prospective tournament follows the same principle for tournament/provider-ops changes. A relevant `main` push may bootstrap the newest eligible immutable current-GW production final into the non-serving tournament, but it cannot run production. Bootstrap source selection requires an immutable actionable still-predeadline final with personalized actionability and unchanged AIrsenal H1-H8 serving authority. `seal-run` then performs the full existing attestation/private-archive/common-snapshot verification. If no eligible source exists, bootstrap is a successful no-op rather than a retrospective reconstruction.

Historical `apex-v2/final/...` tags predate the modern V2 `public_attempt.json` release contract. Bootstrap therefore records them as `MISSING_PUBLIC_ATTEMPT_ASSET` and continues scanning; they are historical ineligible evidence, not a reason to abort discovery of a newer valid V2 final. A release-list/asset-read race is handled the same way. By contrast, once an immutable final advertises the modern asset, run identity, season, authority-field and AIrsenal serving-map corruption still fail closed. The source-resolution record includes examined release count, every rejection and aggregated rejection counts, and is retained as an independent 90-day workflow artifact before sealing.

This distinction was established by live acceptance: the first post-merge tournament run correctly stopped before writing a candidate when its initial scanner encountered legacy final `apex-v2/final/2026-2027/33207047220-1` without `public_attempt.json`. The hardened scanner preserves that event as explicit rejected evidence and proceeds to modern eligible finals instead of masking or treating the old tag as repository corruption.

`Apex V2 Daily Production` intentionally retains no `push` trigger.

## Privacy and no-hindsight boundary

Public production releases contain provider commitments/provenance, not raw third-party forecast rows.

The raw internal forecast surfaces are stored in the immutable private provider-evaluation release and verified against those public commitments.

PITCHSIDE tournament rows are stored only in a separate immutable private tournament supplement. Public tournament records contain source hashes, freshness, coverage counts, entry/DNS state and aggregate post-GW metrics only.

Forecasts are never regenerated after outcomes are known.

## Sequential online specialist learning

The prospective tournament learns after **every completed canonical H1 observation**. Twelve Gameweeks are not a waiting period and are not a gate before Apex may learn from evidence. A longer sample remains useful for a final structural judgment, but live FPL decisions cannot ignore strong repeated evidence while the season is running.

The online-learning layer is deliberately separate from serving authority:

- `production_influence = NONE`;
- `promotion_authority = false`;
- `automatic_serving_change = false`;
- AIrsenal remains the sole serving champion unless a later explicit governed change is separately approved and shipped;
- provider names receive no prior advantage, including Dastan;
- the current qualitative interest in Dastan is a hypothesis to test, not a scoring prior.

### What is learned after every H1

For every provider legitimately entered in the canonical prospective H1 league, the layer retains and compares scoreable sealed components including:

- overall H1 xP MAE and RMSE;
- top-10 and top-25 ranking NDCG;
- catastrophic xP residual rate;
- expected-minutes MAE;
- catastrophic minutes residual rate;
- appearance-probability Brier;
- start-probability Brier when Official supplies an explicit realized start label;
- 60-minute probability Brier;
- position-specific xP and minutes performance;
- pre-outcome minutes-risk cohorts;
- pre-outcome high-disagreement minutes cohorts.

A realized start is never inferred from minutes. If Official does not provide a valid start label, start probability remains `NOT_SCOREABLE_NO_REALIZED_START_LABEL`.

### Specialist cohort construction

Cohorts must be common and outcome-independent so a provider cannot receive a favorable retrospective slice.

Position cohorts use Official season position identity only: `GK`, `DEF`, `MID`, `FWD`.

Minutes-risk cohorts are assigned before looking at results using the median of sealed expected minutes across the entered providers:

- `NAILED_75_PLUS`: consensus expected minutes at least 75;
- `MANAGED_45_TO_74`: consensus expected minutes at least 45 and below 75;
- `ROTATION_RISK_UNDER_45`: consensus expected minutes below 45;
- `UNKNOWN_MINUTES`: fewer than two sealed minutes forecasts exist.

Minutes-disagreement cohorts are also pre-outcome:

- `HIGH_DISAGREEMENT_20_PLUS`: sealed provider expected-minutes range is at least 20 minutes;
- `LOW_DISAGREEMENT_UNDER_20`: range is below 20 minutes;
- `UNKNOWN_MINUTES`: insufficient sealed minutes forecasts.

No player IDs are published in public online-learning summaries.

### Evidence stages

The layer escalates evidence progressively rather than waiting for an arbitrary season length:

- **1 observation — `DIAGNOSTIC_SIGNAL`:** learn immediately, but do not treat the result as actionable proof.
- **2+ observations — `EMERGING_EDGE`:** at least 67% positive-edge rate and at least 3% recency-weighted mean edge.
- **2 observations — `FAST_TRACK_REVIEW_ELIGIBLE`:** both observations are positive wins and the recency-weighted mean edge is at least 10%. This exists specifically so a very large repeated live edge is not ignored for ten more weeks.
- **3+ observations — `ACTIONABLE_SPECIALIST_REVIEW`:** at least 67% positive-edge rate, at least 4% weighted mean edge, and no severe reversal worse than -12%.
- **5+ observations — `SPECIALIST_ROLE_CANDIDATE`:** at least 70% positive-edge rate, at least 5% weighted mean edge and worst edge at least -10%.
- **8+ observations — `STRONG_EVIDENCE`:** at least 70% positive-edge rate and at least 4% weighted mean edge with the same reversal protection.
- **12+ observations — `MATURE_EVIDENCE`:** at least 70% positive-edge rate and at least 3% weighted mean edge with the same reversal protection.

The recent sample is weighted with a four-observation half-life. Older prospective evidence remains part of the record but recent role/minutes changes are allowed to matter more.

`FAST_TRACK_REVIEW_ELIGIBLE` and higher review stages create an owner review item. They do **not** authorize a serving change. The purpose is to identify evidence strong enough to consider a separate governed specialist-role or challenger decision while still preserving the clean experiment.

### Different models may win different jobs

The learning target is not merely one universal winner. The evidence may legitimately establish different specialists, for example:

- one provider for expected minutes and rotation risk;
- another for defender xP;
- another for forward attacking-return ordering;
- another for captain/top-player ranking;
- AIrsenal for strategic H2-H8 planning while a different provider proves stronger at H1 availability.

Any future component-level selection, ensemble, specialist role or champion promotion must be separately designed, audited and approved. This layer only measures and surfaces the evidence required to justify that later decision.

### Immutable sequential evidence chain

After a canonical H1 evaluation exists, the maintenance workflow writes a public aggregate learning snapshot under:

`apex-v2/tournament-learning/<season>/through-obs<N>`

Each snapshot contains aggregate observation metrics and an attestation. Raw provider forecast rows and manager state remain private.

When adding a new observation, the controller:

1. loads the immutable canonical selection and H1 evaluation;
2. reloads the exact sealed private provider surfaces and manager decision surface;
3. fetches Official position identity;
4. re-fetches the realized H1 payload only to enrich the already-scored observation;
5. requires its canonical SHA-256 to exactly equal the immutable H1 evaluation's `official_live_sha256`;
6. requires the recomputed core provider and pairwise metrics to exactly match the immutable evaluation;
7. fails closed rather than reconstructing or backfilling evidence if those identities drift.

Previous observations are carried forward from the prior immutable learning release, so old outcomes are not regenerated retrospectively on every run.

Before the first completed canonical H1, the workflow reports `AWAITING_FIRST_PROSPECTIVE_H1` and publishes no fake observation.

## Failure semantics

The reliability layer distinguishes at least:

- transient infrastructure failure;
- provider logic/invariant failure;
- stale forecast;
- incomplete forecastable universe;
- Official hash mismatch;
- target mismatch;
- post-cutoff submission;
- training not ready;
- training ready but no validated model;
- upstream/readiness availability failure;
- legacy final missing the modern V2 public-attempt asset.

None is silently converted into another provider's forecast.

A real serving defect still fails closed. These extensions do not relax Official parity, AIrsenal freshness/coverage, manager-state verification, solver legality, authentication controls, immutable publication or orphan detection.

## Regression coverage

Operations tests cover:

- exact externalisation set and unchanged AIrsenal serving authority;
- refusal to externalise a serving-authorized provider;
- Dastan transient retry and no retry for logical/invariant failures;
- Dastan pinned-commit health;
- PITCHSIDE unavailable-identity accounting;
- PITCHSIDE missing forecastable-player failure;
- independent H1 versus strategic-horizon qualification;
- OpenFPL immutable moving-history resolution;
- OpenFPL below-floor DNS;
- tournament `TRAINING_READY_NO_MODEL` state after the floor without a model;
- GW2 diagnostic/non-canonical retention;
- GW3 candidate versus postdeadline canonical observation;
- latest-valid-common-predeadline selection;
- privacy/commitment verification;
- post-ops read-only shadow-health trigger;
- post-ops tournament bootstrap eligibility/no-source behavior;
- legacy final missing-asset skip and source-resolution proof retention;
- modern final identity/authority corruption remaining fail-closed;
- proof that production itself still has no push trigger;
- non-serving workflow boundaries;
- common no-hindsight position/minutes-risk/minutes-disagreement specialist cohorts;
- explicit start-label scoring without minutes-based start inference;
- one-observation diagnostic learning;
- two-observation fast-track review for exceptional repeated edges;
- three-observation actionable specialist review;
- simultaneous position-specific leaders from different models;
- provider-name prior neutrality;
- proof that twelve Gameweeks are not a gate to learning or review;
- proof that all online-learning stages retain `NO_AUTOMATIC_CHANGE` serving authority.

The repository operations contract additionally proves that the frozen engine SHA and serving architecture remain unchanged.
