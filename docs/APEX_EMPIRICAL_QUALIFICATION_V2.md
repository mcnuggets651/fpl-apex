# Apex V2 Empirical Qualification Plane

## Purpose

Apex production authority must never reduce an empirical claim to “an immutable artifact exists”. Empirical evidence is only release-authoritative when it is the replay-derived result of a predeclared experiment, bound to the exact proof, subject semantics, season, evaluator, policy, observation window and explicit decision cutoff.

This control plane closes the pre-cutover gap discovered after Slice 13 certification. It does not create or promote any real production champion. The default V2 ExperimentRegistry remains empty until genuine no-hindsight evidence exists.

## Stable pre-qualification subject identity

Several V2 model/policy semantic identities contain `qualification_state` and `qualification_artifact_id`. A certificate cannot target an identity that itself depends on the certificate artifact without creating a content-identity cycle.

`qualification_subject_id()` therefore hashes the full candidate semantic payload after removing only:

- `qualification_state`
- `qualification_artifact_id`

Every other semantic field remains bound. Changing model features, policy settings, horizon, rules, parameters or other candidate semantics changes the qualification subject identity and invalidates qualification reuse.

## Predeclared experiments

`ExperimentDefinition` is immutable and content-addressed. It binds:

- proof or internal qualification ID;
- exact subject kind and stable subject identity;
- season;
- evaluator artifact identity;
- qualification-policy artifact identity;
- declaration time;
- evaluation window start/end;
- minimum sample size;
- exact rational metric thresholds and directions;
- finite validity horizon.

The definition must exist before its evaluation window begins. This is a no-hindsight requirement, not a documentation convention.

`ExperimentResult` is also immutable and binds the registered experiment, subject, evaluator, evaluation completion time, exact metric values, sample size and retained source artifacts.

## Exact qualification semantics

Qualification metrics use rational values rather than floating-point threshold comparisons. The evaluator distinguishes three outcomes:

- `SUPPORTED`: every structural binding is exact, the result is complete and every threshold passes.
- `INCONCLUSIVE`: the structure is valid but evidence is genuinely incomplete, such as insufficient sample size or missing required metrics.
- `REJECTED`: identity/timing/evaluator structure is wrong, unexpected metrics are present, or a qualification threshold fails.

A structural defect remains `REJECTED` even when incomplete evidence is also present. Incompleteness cannot soften tampering or semantic mismatch.

## Replay-derived certificates

An `EmpiricalQualificationCertificate` is not caller-authored authority. It is derived from:

1. one retained ExperimentRegistry artifact;
2. the exact registered ExperimentDefinition artifact;
3. the exact ExperimentResult artifact;
4. all evaluator, policy and source artifacts referenced by those records.

Loading a certificate independently reconstructs and re-derives it. Any missing, corrupt, future, expired, unregistered, mismatched or non-reproducible evidence fails closed.

A certificate is usable only from `first_available_at` and is expired at `valid_until` itself (`as_of >= valid_until`). All production admission uses an explicit replay/decision cutoff; there is no hidden wall clock.

## Constitutional production proof classes

`src/apex_fpl/core/production_proof_contract.py` pins every mandatory production proof ID to its constitutional `ProofClass`. A caller cannot relabel an empirical proof as a formal or algorithmic proof to obtain a PASS ReleaseCertificate.

The mandatory empirical production proofs are:

- `PO-FORECAST-QUALIFICATION-001`
- `PO-DECISION-POLICY-QUALIFICATION-001`
- `PO-SCENARIO-CONVERGENCE-001`
- `PO-MODEL-EVALUATION-001`
- `PO-MODEL-PROMOTION-001`

## Canonical release subject kinds

Every empirical production release proof has exactly one canonical release subject kind:

| Proof | Canonical release subject |
| --- | --- |
| `PO-FORECAST-QUALIFICATION-001` | `apex.forecast-model` |
| `PO-DECISION-POLICY-QUALIFICATION-001` | `apex.decision-policy` |
| `PO-SCENARIO-CONVERGENCE-001` | `apex.scenario-convergence` |
| `PO-MODEL-EVALUATION-001` | `apex.model-evaluation` |
| `PO-MODEL-PROMOTION-001` | `apex.model-promotion` |

The core experiment contracts reject construction of a production-proof definition, result or certificate with any other subject kind.

This distinction is intentional. A qualified scenario generator is not proof that a realised ScenarioSet converged. A qualified learning policy is not proof that a specific model evaluation passed. Those lower-level qualifications can feed a release proof, but cannot impersonate it.

## Internal registry qualification IDs

Lower-level production registry admission uses separate internal qualification IDs:

- `QUAL-SCENARIO-GENERATOR-001`
- `QUAL-SCENARIO-POLICY-001`
- `QUAL-LEARNING-POLICY-001`

Forecast-model and DecisionPolicy qualification correspond directly to their constitutional release subjects, so their registry admission uses their production proof IDs directly.

The reference-solver path remains deliberately separate: `PO-REFERENCE-SOLVER-PARITY-001` is an `ALGORITHMIC_CERTIFICATE` and continues to use the dedicated exact parity/reference-solver certificate contract. It must not be recast as empirical qualification.

## Production registry admission

Production registry verification is typed and time-aware:

- ForecastModel: exact registered champion, `QUALIFIED`, season-valid, explicit `as_of`, replay-valid `apex.forecast-model` certificate.
- DecisionPolicy: exact registered champion, production-qualified receding-horizon policy, explicit `as_of`, no-future availability, replay-valid `apex.decision-policy` certificate.
- Scenario generator: exact champion plus internal `QUAL-SCENARIO-GENERATOR-001` certificate at the Forecast cutoff.
- Scenario convergence policy: exact champion plus internal `QUAL-SCENARIO-POLICY-001` certificate at the Forecast cutoff.
- LearningEvaluationPolicy: exact champion plus internal `QUAL-LEARNING-POLICY-001` certificate at the evaluation cutoff.

A bare SHA, arbitrary JSON artifact, certificate for another proof, certificate for another subject, or certificate outside its availability window is not admissible.

## Production cutover admission

Slice 13 cutover now additionally requires:

- the mandatory proof set is complete;
- every mandatory proof remains `REQUIRED`;
- every mandatory proof retains its canonical ProofClass;
- every satisfying empirical AssuranceClaim contains a replay-valid typed qualification certificate;
- the certificate proof and season match the claim/release;
- the certificate subject identity and experiment identity are explicitly bound into AssuranceClaim evidence IDs;
- authorization replay performs the same checks independently before answer authority can become current.

The existing backend identity, finite release validity, ReleaseCertificate, CAS and exact replay protections remain unchanged.

## Default state and synthetic tests

`config/experiments_v2.yaml` is intentionally empty. This is fail-closed. No production experiment or champion has been fabricated as part of this work.

Tests construct synthetic registered experiments only to prove the control-plane mechanism. Synthetic backend IDs and synthetic qualification certificates in tests are not production evidence and must never be copied into production registries.

## Current production status

This qualification plane removes a machinery and proof-laundering gap; it does not make Apex production-ready by itself. Actual cutover remains WITHHELD until genuine no-hindsight evidence produces qualified champions and a separately proven durable shared ArtifactStore/ReleaseRegistry control plane exists.

At the time this document was added, the production forecast, DecisionPolicy, scenario, reference-solver and learning registries remained without production champions, and the ExperimentRegistry was empty. Those facts are blockers to be resolved with real retained evidence, not configuration values to invent.
