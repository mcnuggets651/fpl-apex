# Apex V2 Production Decision Bundle

## Purpose

A production release must never expose an opaque caller-supplied bundle label. The V2 production bundle is a content-addressed replay contract for the exact direct lineage that produced the user-facing decision.

The bundle exists to answer one question without inference:

> Which exact forecast model, forecast, DecisionPolicy, candidate universe, decision, scenario set and robustness report were used by this production release?

If that question cannot be answered by offline immutable replay, the release is not authoritative.

## Constitutional boundary

`ProductionDecisionBundle` lives in `src/apex_fpl/core/production_bundle.py` and is dependency-free. Its semantic payload commits to:

- season, entry and Gameweek;
- exact `GlobalWorldId`;
- exact `ForecastId` and retained forecast artifact;
- exact `ModelArtifactId` used by the forecast;
- exact `DecisionPolicyId`;
- exact `CandidateUniverseId` and retained candidate-universe artifact;
- exact `DecisionInputId` and `DecisionId` plus retained decision-result artifact;
- exact `ScenarioSetId` and retained scenario-set artifact;
- exact `RobustnessReportId` and retained robustness-report artifact.

`BundleId` is the SHA-256 content identity of that semantic payload. The stored production-bundle artifact contains the raw canonical semantic payload, so its ArtifactStore identity is exactly the same value as `BundleId`.

## Replay contract

`src/apex_fpl/control/production_bundle.py` independently reloads and reconciles every direct dependency before a bundle can be stored or exposed.

Replay requires all of the following to agree exactly:

1. The retained `DecisionResult` re-derives the declared `DecisionId` and `DecisionInputId`.
2. `DecisionInput.decision_policy_id` equals the bundle `DecisionPolicyId`.
3. The exact `DecisionPolicy` semantic artifact exists under that same content identity.
4. The policy is production-qualified, its numeric policy agrees with the `DecisionInput`, and every continuation/chip/price/candidate support artifact replays under the same season/horizon semantics.
5. The retained `CandidateUniverse` has the exact declared identity and exact bundle world.
6. The retained production `Forecast` has the exact declared `ForecastId`, world, season and RuleSet identity used by the decision.
7. The forecast points at the exact declared `ModelArtifactId`.
8. The exact forecast-model semantic artifact, parameters and qualification artifact remain replayable and valid at the forecast cutoff/horizon.
9. The `ScenarioSet` has the exact declared identity, season and forecast and covers the release Gameweek.
10. The `RobustnessReport` has the exact declared identity and binds the same decision, forecast and scenario set.
11. The robustness EV anchor is the selected max-EV decision action.
12. Robustness is `CONVERGED` and xP-reconciled.

Any missing, corrupt, mismatched or semantically different dependency fails closed.

## Direct empirical proof binding

Production cutover derives empirical release subjects from the replayed bundle rather than trusting caller-provided evidence labels.

For the three empirical surfaces that directly determine the released action:

- `PO-FORECAST-QUALIFICATION-001` must qualify the stable pre-qualification subject of the exact replayed `ForecastModelArtifact`; the certificate artifact must be the qualification artifact attached to that model and the exact `ModelArtifactId` must be retained in claim evidence.
- `PO-DECISION-POLICY-QUALIFICATION-001` must qualify the stable pre-qualification subject of the exact replayed `DecisionPolicy`; the certificate artifact must be the qualification artifact attached to that policy and the exact `DecisionPolicyId` must be retained in claim evidence.
- `PO-SCENARIO-CONVERGENCE-001` must qualify the stable subject of the exact replayed `RobustnessReport`; the exact `RobustnessReportId` must be retained in claim evidence.

Every empirical certificate must also carry the canonical production `subject_kind`, exact proof ID, exact season and a replay-valid predeclared experiment identity.

Therefore a valid certificate for model A, policy A or robustness report A cannot authorize a bundle that actually used model B, policy B or robustness report B.

## Publication and answer authority

`execute_production_cutover()` replays the production bundle before deriving publication authorization. A malformed or unrelated bundle cannot become `PUBLISHED`.

`load_production_publication_authorization()` repeats the same bundle replay and exact empirical subject binding during offline authorization replay.

`resolve_production_answer_authority()` independently replays the exact current bundle again before returning `CURRENT`. A current ReleaseRecord whose bundle bytes or dependencies are missing/corrupt becomes `UNAVAILABLE`, even if the release pointer and authorization artifact still exist.

This is deliberate defense in depth: storage, publication replay and answer-time authority each fail closed independently.

## Synthetic tests are not production evidence

`tests/production_bundle_helpers.py` constructs a deterministic synthetic lineage solely to exercise mechanism contracts. Synthetic model/policy/scenario qualifications are test fixtures and must never be registered as production champions or treated as empirical evidence about real FPL performance.

The production registries remain intentionally empty until genuine qualification evidence exists.

## What this does not claim

This contract does not qualify a real forecast model, DecisionPolicy, scenario generator or backend. It does not create a production champion and does not authorize production cutover by itself.

It also does not implement the still-missing executable V2 receding-horizon solver. The bundle guarantees exact lineage for an action that exists; it does not manufacture a production-capable optimiser.

Actual production cutover therefore remains **WITHHELD** until the remaining production qualifications and executable-policy requirements are genuinely satisfied.
