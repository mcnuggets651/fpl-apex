# Apex V2 Probabilistic Forecast

## Purpose

Slice 7 turns one sealed point-in-time `FeatureSnapshot` into replayable probability distributions for future player minutes and FPL points. It does not choose a squad, transfer, captain or chip. Those decisions belong to later slices.

The forecast boundary separates two different authorities that must never be conflated:

1. **Football prediction** — a versioned model may assign probabilities to future football outcomes.
2. **FPL mechanics** — Apex core applies the exact sealed season `RuleSet` to each modelled football outcome to derive FPL points.

A model therefore cannot redefine appearance points, goal values, clean-sheet eligibility, save points, defensive-contribution thresholds, goals-conceded deductions, cards, own goals or bonus points by emitting its own opaque xP number.

## Immutable identities

A compiled `Forecast` binds all of the following:

- `FeatureSnapshotId`
- `GlobalWorldId`
- `RuleSetId`
- `ModelArtifactId`
- `PredictionBatchId`
- `ForecastId`

The prediction batch is persisted before RuleSet scoring. The compiled forecast is persisted afterwards. Both are content-addressed and replayable from `ArtifactStore`.

Forecast compilation exposes no HTTP transport and no clock. The only Official player, club, position, opponent and fixture identities accepted by the production path are rebuilt from the same sealed `GlobalWorld` named by the feature snapshot.

## Probability representation

Durable forecast probabilities use **integer basis points** with denominator 10,000. Scenario probability mass must sum exactly to 10,000 for every predicted player-fixture target.

Expected values are derived from those distributions. For example, `expected_points_numerator` is exact and has denominator 10,000. Binary floating-point values do not enter forecast semantic identity.

A forecast retains distributional information such as:

- minutes p10 / p50 / p90;
- points p10 / p50 / p90;
- appearance probability;
- probability of reaching 60 minutes;
- scenario count and explicit uncertainty kind.

Expected value is not a replacement for uncertainty.

## Official target universe

For a requested gameweek horizon, `build_official_forecast_targets()` reconstructs the target set from the sealed Official FPL bootstrap and fixtures.

- A normal fixture creates one player-fixture target for every current Official player at the involved club.
- A double gameweek creates multiple targets for the same player and gameweek, one per fixture.
- A blank gameweek creates no fixture target for that club.
- Player ID, current club, FPL position, fixture ID, opponent and home/away context come only from the sealed Official world.

Production prediction coverage must exactly equal this universe. Missing targets, invented targets or altered context fail closed. An optimiser must never interpret a missing forecast row as zero value.

## Prediction and abstention

A prediction row is either:

- `PREDICTED`, with explicit scenarios whose probabilities sum exactly to 10,000; or
- `ABSTAINED`, with an explicit reason and no fabricated probability distribution.

Shadow evaluation may preserve abstentions so model failure modes can be measured. Production compilation rejects any abstention across the required Official target universe.

## Future certainty

Ordinary football outcomes remain irreducibly uncertain. A non-degenerate future prediction must be labelled `PROBABILISTIC`.

A degenerate future distribution is accepted on the release path only for a structurally certain **zero-minute** state backed by an official suspension/ineligibility condition. The model cannot declare a player deterministically "nailed for 90" or deterministically certain to score.

Zero-minute scenarios containing goals, assists, saves, cards, bonus or other on-pitch events are invalid.

## Model artifact and no-hindsight validity

`ForecastModelArtifact` declares:

- model name/version;
- feature and prediction contracts;
- immutable parameter artifact IDs;
- qualification state and qualification artifact;
- valid seasons;
- training cutoff (`trained_through`);
- first time the model artifact was available;
- maximum gameweek horizon.

For a historical cutoff T, Apex rejects a model if its training data extends beyond T or if the model artifact itself did not yet exist at T. This is required for honest no-hindsight replay.

The validity horizon is interpreted over the calendar gameweek span, not merely the count of selected gameweek numbers.

## Shadow versus production

`SHADOW` forecasts are retained for evaluation and model research but are not actionable production forecasts.

`PRODUCTION` compilation requires all of the following:

- the model is registered;
- all parameter artifacts verify;
- the qualification artifact verifies;
- the model is `QUALIFIED`;
- the model is the registry's exact champion;
- season, cutoff and horizon are within model validity;
- the prediction batch exactly matches the sealed feature/world identities;
- the prediction batch exactly covers the Official target universe;
- all prediction safety checks pass;
- there are no production abstentions.

`config/forecast_models_v2.yaml` intentionally has `champion_model_id: null` and no production model entries at Slice 7 construction time. Reachability, legacy use, reputation or an attractive backtest is not enough to fabricate a champion.

Slice 11 owns the empirical evaluation, replay, challenger/champion promotion and learning-governance process that can later populate this registry with genuinely qualified artifacts.

## Relationship to later slices

Slice 7 produces per-player/per-fixture forecast distributions and exact FPL point distributions. It does **not** claim that scenario robustness has converged across a full squad decision.

- Slice 8 consumes forecasts with exact FPL state to optimise legal actions.
- Slice 9 owns governed scenario expansion/convergence and robustness diagnostics.
- Slice 10 independently verifies selected decisions/mechanics.
- Slice 11 qualifies predictive models and manages learning/replay.

Until those layers are complete and the forecast registry has a genuinely qualified champion, Apex V2 must not claim a final actionable production recommendation from this Slice alone.
