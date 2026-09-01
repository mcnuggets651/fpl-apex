# Apex V2 Prospective Model Tournament

## Purpose

This document defines the operations-only prospective model tournament for Apex V2. It adds rigorous no-hindsight comparison of forecast providers while leaving the frozen production engine and serving decision untouched.

The production contract remains immutable at engine SHA `99cc7b51b0cff45462b567084cb1844cfe0a456f`:

- AIrsenal is the sole serving champion for H1-H8.
- Apex Proprietary, Dastan and PITCHSIDE are non-serving challengers.
- OpenFPL is a governed diagnostic/shadow provider and may enter only when a valid current-rules model exists.
- No blending, voting, automatic promotion or shadow influence is permitted.
- Tournament records have `production_influence = NONE` and `promotion_authority = false`.
- Production remains independently actionable even when one or more challengers are DNS.

## Why this layer exists

Production qualification and research comparison have different failure semantics. A non-serving provider outage must not make an otherwise valid AIrsenal production decision unactionable, but a tournament must still record the outage explicitly rather than silently dropping the provider.

The tournament therefore creates a separate immutable evidence chain:

1. one production attempt freezes Official FPL and the internal provider surfaces;
2. the tournament verifies that immutable production record and its private provider archive;
3. external PITCHSIDE is captured only if Official FPL still hashes to the exact production snapshot;
4. provider entry/DNS state is sealed before the Official deadline;
5. after the deadline, the last valid common predeadline candidate becomes the canonical prospective observation;
6. scoring occurs only after the corresponding Gameweek outcome is complete.

No forecast can be regenerated after seeing an outcome.

## Provider reliability contracts

### AIrsenal

AIrsenal remains the serving champion and must be H1-H8 qualified in the source production attempt. Any serving-map drift fails the tournament contract closed.

### Apex Proprietary

Apex Proprietary remains SHADOW and is expected to support H1-H8. It can enter the Universal H1 league and Strategic H2-H8 league when its exact sealed production surface is qualified.

### Dastan

The September 1 production evidence did not show a Dastan model failure. Dastan was HEALTHY and H1 qualified. The reliability defect was operational: each live acquisition cloned and installed a pinned upstream, exposing the shadow to transient DNS/Git/PyPI/network faults.

The operations repair adds:

- exact pinned-upstream preflight;
- bounded retry only for transient infrastructure failures;
- no retry for Official-hash mismatch, schema/model errors or failed invariants;
- an explicit health artifact and attempt count;
- no serving authority.

Dastan is currently H1-only, so it may enter Universal H1 without being excluded merely because it lacks H2-H8.

### OpenFPL

OpenFPL is not allowed to reuse legacy weights under 2026/27 scoring. The governed training policy requires at least 10 completed exact-rule 2026/27 Gameweeks.

Readiness is evaluated against a moving public history branch, but every check resolves that branch to an exact immutable commit and records a manifest hash. Only rows for Gameweeks that Official FPL marks both `finished=true` and `data_checked=true` count toward the floor.

States are explicit:

- `TRAINING_NOT_READY`: fewer than 10 exact-rule completed Gameweeks;
- `TRAINING_READY_NO_MODEL`: the history floor has been met but no separately validated current-rules OpenFPL forecast export exists;
- `ENTERED`: possible only after a valid predeadline OpenFPL surface exists and passes the same tournament contract as any other entrant.

There is intentionally no ad-hoc OpenFPL retraining pipeline. The pinned upstream exposes a method/notebook and sample-data workflow, not a reproducible current-rules production builder whose scientific assumptions can be safely inferred. The tournament therefore fails visibly at `TRAINING_READY_NO_MODEL` rather than fabricating a model.

### PITCHSIDE

PITCHSIDE is an independently scheduled external publication. Its forecast does not need to be generated after the Apex attempt starts; it must instead be fresh, aligned to the exact target Gameweek, generated before the Official deadline and captured against the exact same Official FPL snapshot hash.

Identity is exact only:

`PITCHSIDE player_code -> Official FPL fpl_code -> Official element_id`

No fuzzy names are used.

The forecast universe is also explicit. Official players with `status = u` are retained in the private surface as:

- `coverage_status = NO_FORECAST`
- `coverage_reason = OFFICIAL_UNAVAILABLE_NO_FORECAST_EXPECTED`

They are not counted as missing model forecasts. Every other Official player is forecastable and must have a finite PITCHSIDE value at each claimed horizon. A missing active/injured/doubtful/suspended player produces `DNS / INCOMPLETE_UNIVERSE`; nothing is filled with zero, interpolation, AIrsenal or postdeadline data.

This corrects the earlier blanket 626/626 interpretation. The inspected September 1 PITCHSIDE artifact contained 626 identities, 575 forecast vectors and exactly 51 `status=u` omissions; all 575 forecastable players had GW3-GW19 vectors.

## Privacy and commitment/reveal

Public tournament releases never contain third-party raw forecast rows.

The public source production release contains provider provenance commitments only. The corresponding immutable private evaluation release contains the raw internal provider surfaces and is verified against those public commitments.

PITCHSIDE is captured separately and written only to the private immutable tournament supplement. The public candidate contains its hashes, counts, freshness and entry/DNS classification.

Private manager state is used after the Gameweek only to reconstruct the already-frozen model-neutral H1 decision surface. It is never written to a public tournament artifact.

## Common snapshot rule

A tournament candidate is eligible only when all of the following are true:

- the source production final is immutable;
- its private provider-evaluation release is immutable and verifies against public commitments;
- the source production attempt is actionable;
- AIrsenal is still the sole serving champion H1-H8;
- all required internal providers are explicitly present;
- current Official FPL hash equals the production attempt Official hash before external PITCHSIDE acquisition;
- PITCHSIDE is captured before the target deadline or is explicitly DNS;
- OpenFPL is explicitly ENTERED or DNS with a governed reason;
- every expected provider is accounted for;
- at least one challenger is entered in Universal H1;
- the candidate itself is sealed before the Official deadline.

An external provider can be DNS without blocking production or, by itself, blocking the tournament candidate. Silent provider omission is forbidden.

## Candidate and canonical observation

Before deadline a valid run is only:

`PROSPECTIVE_READY_CANDIDATE`

It has no official win/loss and no prospective observation number.

After the target deadline the controller selects:

`LAST_VALID_COMMON_PREDEADLINE_SEAL`

among all immutable ready candidates for that Gameweek. The selected record becomes:

`CANONICAL_PROSPECTIVE_OBSERVATION`

This prevents an early Tuesday run from displacing a fresher legitimate Friday predeadline run.

GW3 is the first Gameweek eligible for the canonical prospective series. If the GW3 seal contract passes, it becomes `prospective_observation_number = 1` after the September 4, 2026 deadline.

## GW2 treatment

GW2 evidence is retained as:

`DIAGNOSTIC_REHEARSAL_NON_CANONICAL`

The record preserves useful existing comparisons but explicitly sets:

- canonical prospective win/loss: forbidden;
- promotion/demotion evidence: forbidden;
- retrospective reconstruction: forbidden.

GW2 can never consume prospective observation number 1.

## Tournament leagues

### Universal H1

Universal H1 compares every legitimate H1 entrant independently of longer-horizon capability. Dastan is therefore eligible even though it currently supports H1 only.

Expected field when healthy:

- AIrsenal
- Apex Proprietary
- Dastan
- PITCHSIDE
- OpenFPL only after a legitimate current-rules model exists

### Strategic H2-H8

Strategic horizons contain only providers that sealed the corresponding horizon. H1 qualification is not enough to imply H2-H8 entry.

Each horizon is evaluated only when its realized Gameweek finishes. For a GW3 observation:

- H1 is scored after GW3;
- H2 after GW4;
- ...
- H8 after GW10.

Future outcomes are never fetched early and later-horizon values are never collapsed into an immediate synthetic score.

## Forecast scoring

The controller reuses the frozen Apex evaluation primitives rather than creating a competing metric engine.

H1 uses the frozen `MODEL_NEUTRAL_DECISION_SURFACE_V1`, a union of the manager's sealed squad/decision path and provider-neutral candidate surfaces. Aggregate provider metrics and pairwise comparisons are calculated only over prospectively sealed forecasts.

H2-H8 use full eligible forecast overlap because a future manager decision surface was not known at the original target-GW seal.

Public evaluation artifacts contain aggregates, never raw player forecast rows or player-level outcome tables.

## Specialist/component scoring

Component diagnostics are scored only when that component was sealed prospectively and a legitimate realized label exists. Supported examples include:

- expected-minutes MAE;
- appearance-probability Brier score;
- start-probability Brier score when realized-start labels exist;
- 60-minute probability Brier score when sealed and labelable;
- catastrophic xP residual counts.

Attacking-return, clean-sheet and bonus component scores remain `NOT_SCOREABLE` unless the provider actually sealed the corresponding component prediction. Missing components are never reverse-engineered from xP after the result is known.

## Decision quality

Forecast accuracy and decision quality are separate evidence domains.

The existing private decision-quality pipeline measures the realized consequences of the prospectively sealed manager decision. Tournament evaluation links to the corresponding private decision-quality release by run identity but does not mix those values into forecast MAE/RMSE or provider ranking.

## Market benchmark

Market evidence is an auxiliary benchmark, not a fake player-projection entrant. It may eventually provide team-strength, win, clean-sheet, goals or scorer priors when an immutable predeadline market artifact exists.

No such immutable benchmark is currently established in the repository, therefore the tournament records:

`market_benchmark.status = UNAVAILABLE`

This does not block projection-provider readiness and market information cannot override inferior football EV.

## DNS reason codes

The controller records exact reasons including:

- `TRAINING_NOT_READY`
- `TRAINING_READY_NO_MODEL`
- `PROVIDER_EXPORT_MISSING`
- `INCOMPLETE_UNIVERSE`
- `FORECAST_STALE`
- `SCHEMA_INVALID`
- `OFFICIAL_HASH_MISMATCH`
- `TARGET_MISMATCH`
- `SUBMISSION_AFTER_CUTOFF`
- `NO_H1_FORECAST`
- `ARTIFACT_HASH_MISSING`
- `UNQUALIFIED`
- `UPSTREAM_UNAVAILABLE`

DNS is data, not an excuse to omit the provider.

## Reliability ledger

Across candidate attempts, the status surface tracks per provider:

- expected attempts;
- entered submissions;
- DNS count and reasons;
- submission rate;
- source age/freshness at seal;
- horizon coverage;
- forecastable-universe coverage;
- unavailable-universe accounting.

Operational reliability remains separate from forecast skill.

## Immutable release namespace

Public:

- `apex-v2/tournament-candidate/{season}/{run_id}`
- `apex-v2/tournament-selection/{season}/gw{gw}`
- `apex-v2/tournament-evaluation/{season}/obs{n}/h{h}`
- `apex-v2/tournament-diagnostic/{season}/gw2`

Private:

- `apex-v2/private-tournament/{season}/{run_id}`

Every release is create-once and requires repository release immutability.

## Automation

`Apex V2 Prospective Tournament` runs in two modes:

- after a successful `Apex V2 Daily Production`, it seals a candidate for that exact production run;
- hourly maintenance retains GW2 diagnostics, canonicalizes any deadline-passed observation, scores newly completed horizons and materializes the public status artifact.

The workflow checks out the frozen engine SHA and materializes the exact four-module tournament operations controller from the current control-plane SHA. It has no FPL owner cookies/tokens, cannot run `apex-v2 solve`, cannot publish a production decision, cannot acquire AIrsenal/Dastan and cannot dispatch production.

The private release token is present only because exact prospectively sealed provider surfaces and manager-decision identity are stored in the separate private immutable repository.

## GW3 readiness statement

A predeadline status of:

`GW3 PROSPECTIVE TOURNAMENT READY = TRUE`

means there is at least one immutable `PROSPECTIVE_READY_CANDIDATE` satisfying the common-snapshot contract. It does **not** mean Observation #1 has already been declared.

Only after the Official GW3 deadline may the hourly controller choose the last valid common predeadline seal and publish canonical Prospective Observation #1.
