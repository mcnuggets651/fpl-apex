# Apex V2 Champion Authority

## Purpose

Empirical qualification and production selection authority are separate controls. A candidate may be SHADOW or QUALIFIED without being the production champion. PR #87 adds the immutable reviewed authority chain that production publication must replay before any qualified candidate can become user-facing authority.

This document describes mechanism and governance only. It does not assert that a real production champion, deployed production control plane or production release currently exists.

## Authority roles

One production champion generation binds four decision-critical identities:

1. forecast model;
2. DecisionPolicy;
3. scenario generator;
4. scenario policy.

The exact identities must match the already replayed schema-v2 `ProductionPlanningBundle`. An independently valid but different champion is insufficient.

## Forecast-model authority

Forecast authority reuses the existing learning-governance chain rather than inventing a second model registry:

`production evaluation -> exact comparison -> ModelPromotionCertificate -> ModelRegistryGeneration -> forecast champion`

A retained `PROMOTE` label is not sufficient. Runtime replay locates the exact retained candidate and incumbent `ModelEvaluationReport` artifacts, the exact `ModelComparisonReport`, and the exact retained qualified champion `LearningPolicyRegistry` used by the promotion. It reconstructs those typed objects, reconciles their semantic identities and common-truth lineage, checks the comparison rows against the retained evaluation metrics, replays the learning policy at the generation authorization time, and re-runs the existing promotion threshold/interval logic. The registry champion is accepted only when that independent replay derives the same promotion identity and still derives `PROMOTE` for the exact candidate named as champion.

A hand-authored promotion certificate, a model evaluation, a comparison, a QUALIFIED model artifact or an arbitrary registry row therefore cannot establish forecast champion authority.

## DecisionPolicy, scenario-generator and scenario-policy authority

These three roles use an explicit `ChampionAdmissionCertificate`. Admission requires:

- the exact candidate semantic identity;
- a replay-valid typed empirical qualification for the required subject kind and proof/qualification ID;
- retained immutable review evidence;
- reviewer identity, review time and reason;
- exact season binding.

For a materialized QUALIFIED `DecisionPolicy`, the policy must also name the exact empirical qualification artifact being replayed. The central empirical subject identity remains the existing stable pre-qualification identity, which removes only `qualification_state` and `qualification_artifact_id`; #87 does not redefine that contract.

Qualification therefore does not silently confer champion status. Admission is a distinct reviewed operation.

## ProductionChampionGeneration

The four authorities are composed into one immutable `ProductionChampionGeneration`. Each generation records:

- exact season;
- generation number;
- optional parent generation artifact;
- exact forecast model-registry generation and resulting model champion;
- exact admission artifacts and candidate identities for DecisionPolicy, scenario generator and scenario policy;
- retained change-control evidence;
- authorizer identity, timezone-aware authorization time and reason.

Generation creation is stale-writer-safe. If a current generation exists, the caller must supply the exact expected parent semantic identity. A stale writer cannot create the next authoritative generation.

Authority is also point-in-time. Review and generation authorization timestamps must be timezone-aware. An admission cannot replay before its own review time; a generation cannot replay before its own authorization time; and every component admission plus the parent generation must already have been valid at the child generation's authorization time. Future review or authorization evidence cannot leak backward into an earlier production decision.

Replay verifies recursive parent continuity, season, retained change-control evidence, independently re-derived forecast promotion lineage, and all three reviewed admissions with their typed empirical qualifications.

## Bundle reconciliation

`verify_bundle_champion_authority` independently replays the generation and then exact-matches:

- generation forecast model == bundle forecast model;
- generation DecisionPolicy == bundle DecisionPolicy;
- generation scenario generator == bundle `ScenarioSet.scenario_generator_id`;
- generation scenario policy == bundle `RobustnessReport.scenario_policy_id`.

There is no fuzzy matching, name matching or configuration fallback.

## Publication binding

Production publication authorization moves to schema v2 and carries `champion_generation_artifact_id`.

A WITHHELD attempt may retain no champion generation so the failed attempt remains auditable. `ProductionPublicationAuthorization.authorized` can never become true unless a champion-generation artifact is present.

When a generation is supplied, cutover verifies its immutable artifact and independently replays it against the already verified production planning bundle before sealing authorization. The champion-generation artifact is retained in publication lineage.

Missing, corrupt, expired, wrong-season or bundle-mismatched champion authority fails closed and cannot advance the production current pointer.

## Answer-authority replay

Answer authority does not trust cutover's earlier interpretation. Resolving a current user-facing V2 answer independently:

1. replays the current immutable `ReleaseRecord`;
2. replays publication authorization;
3. replays the schema-v2 production planning bundle;
4. independently replays the champion generation again against that bundle;
5. replays backend qualification against the actual live backend identities;
6. rechecks the production current pointer before returning authority.

If any authority identity diverges, the result is `UNAVAILABLE`, never a manually selected fallback recommendation.

## Administrative versus runtime boundary

Champion admission and generation creation are administrative reviewed operations. Runtime publication and answer-authority code are verifier-only: they may load/replay/compare authority artifacts but must not call `issue_champion_admission` or `create_production_champion_generation`.

Candidate qualification remains separate from champion admission. The `apex-v2` prospective-operations path must not auto-promote or auto-admit a champion.

## Synthetic test evidence

The test suite constructs mechanism-only authority artifacts so replay, stale-writer behavior, exact candidate matching, missing review evidence and publication/answer gating can be exercised deterministically. These synthetic artifacts are not real production qualifications, reviews, champions or operational evidence.

## Production status

Engineering implementation of the authority mechanism does not create a real champion. Actual V2 production remains WITHHELD until genuine prospective qualifications/reviews, exact deployed backend Plane-B evidence, a real production planning bundle, complete AssuranceCase, exact reference-solver authority and the full replayed publication chain pass inside the release validity window.

## Engineering certification scope

PR #87 may be called engineering-certified only from one exact human-authored frozen head that completes both normal Apex CI and V2 Shadow Production. `action_required`, cancelled, superseded or intermediate heads are not certification evidence. Apex CI must include the focused champion-authority/cutover/answer-authority contracts, full pytest, full Ruff, upstream pins, governance consistency and immutable build/SBOM/provenance evidence. That engineering certificate never substitutes for the genuine production evidence required above.
