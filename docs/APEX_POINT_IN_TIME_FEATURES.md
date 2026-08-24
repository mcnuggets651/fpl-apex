# Apex V2 Point-in-Time Features and Minutes Inputs

## Purpose

Slice 6 establishes the feature-time boundary used by every later forecast, replay and decision. It proves what Apex could know at cutoff `T`; it does **not** claim that a predictive model mapping those facts to future minutes or FPL points is already qualified.

## FeatureSnapshot

A `FeatureSnapshot` is an immutable semantic object identified by `FeatureSnapshotId`. It records:

- season;
- exact decision cutoff;
- the sealed `GlobalWorldId` it derives from;
- canonical feature observation IDs;
- the complete immutable input artifact set.

Every `FeatureObservation` records:

- canonical feature name and scope/entity;
- typed value (`INTEGER`, `BOOLEAN`, `CATEGORICAL`, or explicit `MISSING`);
- observation time;
- first-known time;
- immutable source artifact IDs;
- derivation identity.

An observation first known after the snapshot cutoff is rejected. Duplicate canonical feature keys are rejected instead of resolving by input order.

## No implicit defaults

Missing information is not equivalent to a neutral-looking number. Examples:

- absent Official availability chance is `MISSING`, not 100%;
- absent prior/preseason minutes are `None`, not zero;
- absent fixture/team evidence is not a hidden multiplier of `1.0`;
- expected minutes is not defaulted to `70` or any other constant.

`MISSING` and a real observed zero have different semantic identities.

## Sealed Official features

`official_player_feature_observations()` consumes a previously sealed Official FPL `GlobalWorld`. It exposes no network or clock port and requires every capture used by the world to have been retrieved by the requested cutoff.

The initial direct feature surface contains:

- Official price in integer tenths;
- Official team ID;
- Official position ID;
- cumulative FPL minutes;
- cumulative FPL starts when present;
- Official chance-of-playing field in basis points when present;
- Official status.

The producer never fetches Understat or another external provider during transformation.

## Derived feature batches

Historical, preseason and other derived facts enter through immutable `FeatureBatch` artifacts. A batch has its own `available_at`, producer ID and source-artifact lineage.

A batch created or becoming available after cutoff `T` cannot be used by a FeatureSnapshot at `T`, even when its underlying observation happened earlier. This prevents a later-corrected database or post-event rebuild from laundering future information into a historical replay.

## Cross-season identity

Prior-season samples are keyed by `PersonId` and attach to the current Official FPL player only through a reviewed `PersonLink`. Names and assumed continuity of FPL integer IDs are not identity authority.

## Preseason minutes facts

`PreseasonAppearance` records only facts that were known at the cutoff: match time, minutes, whether the player started, first-known time and immutable source artifact.

The derived preseason surface records totals, appearance/start counts, latest appearance minutes/start state and consecutive recent starts. An isolated cameo remains an isolated cameo fact; repeated starts remain repeated-start facts. Feature engineering does not decide how much those facts should move expected minutes.

That weighting belongs to the empirically qualified probabilistic minutes model in Slice 7.

## MinutesFeatureVector

`MinutesFeatureVector` is a no-default model-input contract. It exposes:

- Official status/chance;
- current cumulative sample;
- prior-season minutes/starts/appearances when known;
- preseason minutes/starts/appearances when known;
- exact contributing observation IDs;
- explicit missing-feature names.

It deliberately has no `expected_minutes` field. Manual/tactical `expected_minutes_override` is not V2 authority.

## Outcome truth registry

Calibration/evaluation targets use `config/outcome_truth_v2.yaml`. Every supported target must be either `VERIFIED` with a named field/source contract or explicitly `UNRESOLVED`.

Currently verified from retained Official FPL surfaces are FPL points, FPL minutes, prices, goals and FPL assists. Start/lineup, underlying xG/xA and defensive-contribution truth remain unresolved until their canonical post-event authority is explicitly verified.

Experiments may not silently choose a convenient provider for an unresolved target.

## Architecture prohibitions

Slice 6 feature-control modules are architecture-tested against:

- V1 `apex_fpl.data` and `apex_fpl.services` dependencies;
- pandas/dataframe runtime dependence;
- `requests`/`httpx` network access;
- `CachedHttp`;
- wall-clock reads;
- `fetch_understat` inside transformation;
- `expected_minutes_override`.

## Proof obligations

Slice 6 adds:

- `PO-FEATURE-TIME-TRAVEL-001` — cutoff and lineage prevent future leakage;
- `PO-OUTCOME-TRUTH-001` — calibration truth authority is explicit;
- `PO-MINUTES-FEATURE-INPUT-001` — minutes inputs preserve exact facts/missingness and do not write the prediction.

Forecast accuracy, calibration and probabilistic minutes quality remain empirical claims for Slice 7 / later learning governance.