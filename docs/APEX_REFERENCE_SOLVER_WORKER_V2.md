# Apex V2 Isolated Reference Solver Worker

## Status

This document defines the V2 external reference-solver worker and its algorithmic qualification boundary.

The worker is an **independent assurance mechanism**. It is not the production DecisionEngine, does not choose a competing live team, and does not become production authority merely because its tests or qualification replay pass.

The governed registry in `config/reference_solvers_v2.yaml` remains fail-closed with no production champion until a worker whose declared scope matches the active production DecisionPolicy is explicitly admitted with retained qualification evidence.

The current `apex-isolated-reference-solver` v1 contract is tactical current-Gameweek only. It must not be promoted as a receding-horizon production worker.

## Independence boundary

The worker consumes only the sealed data-only `ReferenceSolverRequest` contract. Its implementation is prohibited from importing:

- `apex_fpl.decision`;
- `apex_fpl.optimisation`;
- `apex_fpl.services`;
- `apex_fpl.assurance.reference_mechanics`.

It independently implements legal squad/action search, finance, transfer-hit accounting, XI selection, captain/vice handling and probabilistic autosub mechanics using exact rational arithmetic.

The worker has an explicit search-node budget. Exhausting that budget yields `SOLVER_LIMIT`; incomplete search cannot be labelled `OPTIMAL`.

## Sealed request and output replay

`ReferenceSolverRequest` embeds canonical semantic JSON for the exact:

- `DecisionInput`;
- `ManagerState`;
- `Forecast`;
- `CandidateUniverse`;
- `RuleSet`;
- `DecisionPolicy`.

The request constructor cross-checks all semantic identities before sealing the artifact.

`ReferenceSolverRun` binds the exact request ID and preserves typed termination state, exact objective/bound/gap, selected action identity, action-surface completeness, tie-break identity and search counts.

A `ReferenceSolverCertificate` may be constructed only by replaying the retained request and run artifacts. Parity validation replays those same bytes again. Merely storing arbitrary input/output bytes is not solver evidence.

## Typed identity boundary

Apex semantic IDs are intentionally non-interchangeable typed value objects. Certificate construction therefore converts retained request hashes into the corresponding `DecisionInputId`, `CandidateUniverseId` and `DecisionPolicyId` types before they can enter assurance.

String/hash equality at the serialized worker boundary is normalized explicitly; typed IDs are preserved inside Apex authority contracts.

## Algorithmic qualification

A worker marked `QUALIFIED` must carry a replay-derived `ReferenceSolverAlgorithmicQualificationCertificate`. A random SHA, a file that merely exists, a historical V1 solver artifact, or a manually asserted status cannot satisfy the registry.

Qualification re-executes every retained corpus case through the isolated worker and requires exact parity with the retained Apex `DecisionResult` for:

- `DecisionInputId`;
- `CandidateUniverseId`;
- `DecisionPolicyId`;
- exact objective;
- selected action identity;
- declared horizon and solver contract.

Qualification is bound to a stable prequalification worker subject identity that excludes only `qualification_state` and `qualification_artifact_id`. Changing worker code, contract, scope, version or availability semantics changes the subject.

## Mandatory derived coverage

A replayable corpus is not sufficient by itself. Qualification is refused unless the retained cases **demonstrably derive** every mandatory coverage tag below:

1. `PROBABILISTIC_AUTOSUB` — a selected XI player has non-zero no-appearance probability, exercising expected autosub mechanics.
2. `DOUBLE_GAMEWEEK` — a selected XI player has multiple fixture rows in the same Gameweek, exercising gameweek aggregation.
3. `TRANSFER_FINANCE` — the selected action executes a transfer.
4. `SELLING_PRICE_RESOURCE` — an outgoing player has a nontrivial purchase/current/selling-price relationship, exercising realized FPL selling value rather than current market price.
5. `PAID_HIT` — the selected action incurs transfer-hit points.
6. `TRIPLE_CAPTAIN_SURFACE` — the declared search includes Triple Captain and completes exactly.
7. `BENCH_BOOST_SURFACE` — the declared search includes Bench Boost and completes exactly.
8. `WILDCARD_SURFACE` — the declared search includes Wildcard and completes exactly.
9. `FREE_HIT_SURFACE` — the declared search includes Free Hit and completes exactly.
10. `TIE_BREAK_PARITY` — the retained Apex result contains a different equal-objective alternative and the worker selects the same canonical tie-break winner.

These tags are derived from retained request/result bytes. Callers cannot supply or self-attest them. A one-case or otherwise weak corpus that does not prove the full set is rejected even when every included case replays successfully.

## Registry and authorization

`ReferenceSolverRegistry.verify_certificate_worker(..., production=True)` requires all of the following:

- exact registered worker identity;
- exact worker code artifact;
- worker availability for season/cutoff/horizon;
- worker is the registered champion;
- replay-valid algorithmic qualification certificate covering the decision season/horizon.

Successful authorization is itself retained and replayable. Historical replay reopens the retained registry snapshot and re-verifies qualification rather than trusting a past boolean.

## Deliberate non-claims

This implementation does **not** assert that:

- the tactical v1 worker is a valid production receding-horizon solver;
- any reference-solver champion currently exists;
- passing synthetic/adversarial qualification cases proves forecast or football-model correctness;
- PR #66 or its open-solver scripts are V2 production authority;
- a green engineering workflow alone authorizes publication.

Actual production cutover remains governed by the full V2 proof surface, qualified champions, durable backend authority and publication/release contracts.