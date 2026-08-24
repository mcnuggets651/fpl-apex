# Apex V2 Slice 11 — Replay and Learning Governance

## Purpose

Slice 11 makes model learning auditable without allowing hindsight, mutable evaluation state, implicit truth providers or automatic online champion changes.

Learning is offline. The sealed production forecast/decision runtime never retrains itself and never changes a champion because a metric looked better during a live run.

## Immutable lifecycle

The governed sequence is:

`ModelTrainingRun -> EvaluationDataset -> EvaluationObservationSet -> ModelEvaluationReport -> ModelComparisonReport -> ModelPromotionCertificate -> ModelRegistryGeneration`

Every stage has deterministic semantic identity. Every downstream stage replays the exact stored semantic object it consumes rather than accepting an arbitrary artifact that merely exists.

Evaluation is evidence. Comparison is evidence. Promotion is a separate decision artifact. Registry mutation is a separate CAS-style transition.

## No hindsight

A training run declares:

- model artifact identity;
- training cutoff;
- first-available time;
- immutable training datasets;
- trainer-code artifact;
- parameter artifacts;
- complete source lineage.

For every evaluation case:

- the prediction is sealed before the outcome becomes available;
- the training run must already have been available when that prediction was sealed;
- the training cutoff cannot be after the prediction seal;
- prediction and outcome artifacts are separate immutable evidence.

A production learning policy must also have existed before the evaluation outcome window began. Thresholds cannot be selected after seeing the evaluation results.

## Truth authority

`OutcomeTruthRegistry` is the only authority for deciding whether a post-event target is currently evaluable.

As currently configured:

- FPL_POINTS — VERIFIED;
- MINUTES — VERIFIED;
- PRICE — VERIFIED;
- GOAL — VERIFIED;
- ASSIST — VERIFIED;
- START — UNRESOLVED;
- LINEUP — UNRESOLVED;
- UNDERLYING_XG — UNRESOLVED;
- UNDERLYING_XA — UNRESOLVED;
- DEFENSIVE_CONTRIBUTION — UNRESOLVED.

An unresolved target remains `INCONCLUSIVE`. In particular, START truth is not inferred from minutes.

The retained truth-registry bytes are replayed and must reconstruct the exact semantic `OutcomeTruthRegistryId` named by the evaluation dataset.

For every currently VERIFIED Official-FPL target, the evaluator does not trust a supplied normalized `actual_value`. It independently recomputes the exact actual from the retained canonical raw artifact and exact Official player ID before any metric is allowed to run:

- FPL_POINTS -> retained Official FPL event-live `stats.total_points`;
- MINUTES -> retained Official FPL event-live `stats.minutes`;
- GOAL -> retained Official FPL event-live `stats.goals_scored`;
- ASSIST -> retained Official FPL event-live `stats.assists`;
- PRICE -> retained Official FPL bootstrap `now_cost` at that captured point in time.

The raw normalizer is strict: malformed JSON, non-integer/bool-laundered values, duplicate/missing Official player rows, source-capability mismatch, missing/corrupt artifacts or disagreement between the retained raw value and the normalized observation reject evaluation. Therefore realized truth is not merely common across candidate and incumbent; it is also reconciled to the declared canonical truth authority.

## Common truth fairness

Two different identities are deliberately retained.

### EvaluationTruthSetId

This is model-independent source truth identity. It binds the exact season, truth registry and player/Gameweek/target outcome cases, including retained outcome artifact identity and first-available time.

Candidate and incumbent model comparisons require the same `EvaluationTruthSetId`.

### EvaluationRealizedTruthSetId

This is model-independent normalized realized truth identity. It binds every truth-case ID to the exact rational actual value used by evaluation.

Candidate and incumbent comparisons also require the same `EvaluationRealizedTruthSetId`.

Therefore two models cannot be compared if they reference different source truth cases or different normalized outcomes. For VERIFIED Official-FPL targets, those normalized outcomes must first reconcile exactly to the retained canonical raw bytes.

Missing predictions are represented explicitly as `predicted_value=None`; they do not remove the corresponding actual outcome from the observation set. This keeps the realized truth set complete while allowing prediction coverage to be measured honestly.

## Exact metrics

Durable metrics and thresholds use `ExactMetricValue`, a reduced rational representation. Binary floating-point values are not part of semantic learning evidence.

The player-outcome evaluator currently supports exact forms of:

- START_BRIER, when START truth is verified;
- MINUTES_MAE;
- MINUTES_MSE;
- POINTS_MAE;
- POINTS_MEAN_BIAS;
- INTERVAL_COVERAGE;
- PREDICTION_COVERAGE.

`DECISION_REALIZED_POINTS_DELTA` is intentionally not fabricated from player-level observations. A policy requiring it remains `INCONCLUSIVE` until a separate sealed decision-impact evaluator exists.

Insufficient sample size, missing required intervals, unresolved truth, unsupported cohort evidence or missing policy authority remain explicit blockers.

## Shadow versus production

`LearningUseMode` is semantic identity.

A shadow evaluation can be mathematically complete, but it cannot be laundered into production promotion evidence.

Production evaluation requires:

- a production-qualified learning policy;
- immutable policy qualification and promotion-rule artifacts;
- season validity;
- a registered champion learning policy;
- retained registry bytes that reconstruct the exact registry object;
- policy availability before the evaluation outcome cutoff.

The repository intentionally ships `config/learning_policies_v2.yaml` with no champion and no fabricated qualified policy.

## Predeclared promotion rules

A learning policy contains typed per-metric promotion rules rather than an opaque `better=true` flag.

Each rule binds:

- metric;
- outcome target;
- cohort;
- direction (`LOWER_IS_BETTER`, `HIGHER_IS_BETTER`, or `CLOSER_TO_ZERO`);
- exact minimum improvement;
- optional interval-superiority requirement.

A qualified policy requires one promotion rule for every required metric.

Candidate and incumbent reports must use the same policy, same use mode, same source truth set and same realized normalized truth set.

## Promotion and champion mutation

A `ModelComparisonReport` does not change the champion.

`ModelPromotionCertificate` is issued separately and can be:

- PROMOTE;
- RETAIN;
- INCONCLUSIVE.

The promotion issuer replays:

- candidate evaluation artifact;
- incumbent evaluation artifact;
- comparison artifact;
- learning-policy registry bytes;
- policy qualification/rule artifacts.

Only a COMPLETE production comparison under the still-authoritative qualified champion learning policy can produce PROMOTE.

Champion mutation occurs only through `apply_model_promotion()` and an immutable parent-linked `ModelRegistryGeneration`.

The transition is compare-and-swap style:

- supplied parent generation must equal the current generation identity;
- only PROMOTE certificates may mutate the champion;
- candidate and incumbent must already be registered;
- when a current champion exists, the certificate incumbent must equal that champion;
- the next generation retains the current generation and promotion artifacts in its lineage.

Storage and replay additionally require that a champion-bearing registry generation's source lineage contain exactly one retained `MODEL_PROMOTION_CERTIFICATE` whose semantic promotion identity equals the generation's declared `promotion_id`. A valid but unrelated promotion artifact cannot authorize the champion.

A stale writer fails rather than overwriting a newer registry generation.

## Replay and artifact integrity

Learning objects are stored in one canonical content-addressed envelope.

Replay checks:

- canonical JSON;
- object type;
- semantic ID recomputed from payload;
- expected semantic ID when supplied;
- unique/canonical parent and source arrays;
- existence/integrity of every retained parent/source artifact;
- exact promotion-certificate authorization for champion-bearing registry generations.

A valid but unrelated learning artifact cannot satisfy another object's dependency merely because its SHA-256 exists.

## Architecture boundary

Slice 11 core/control learning modules and retained outcome normalization may not depend on:

- V1 `apex_fpl.evaluation` or `apex_fpl.replay`;
- V1 data/services runtime paths;
- pandas, numpy or scipy;
- runtime RNG;
- requests/httpx;
- wall-clock reads inside the learning path.

Core remains dependency-free. Control owns artifact/replay/admission and canonical truth-normalization operations.

## Production state after Slice 11

Slice 11 creates the machinery to evaluate and govern model promotion. It does **not** fabricate empirical evidence that does not yet exist.

No forecast model is promoted merely because this slice exists. No learning policy champion is invented. Unresolved truth targets remain unresolved.

The next slice, V2 shadow production, must exercise these contracts prospectively before production cutover.
