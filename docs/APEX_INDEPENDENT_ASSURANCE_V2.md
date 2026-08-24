# Apex V2 Independent Decision Assurance

## Status

Slice 10 defines an independent assurance layer for one already sealed V2 `DecisionResult`. It does **not** optimise a competing live team, mutate the selected action, fetch new football data, or replace the DecisionEngine. Its only authority is to certify, block, or remain inconclusive about a decision that already exists under exact semantic identity.

## Why this layer exists

A production optimiser must not be its own sole witness. Slice 8 already carries exactness, legality and mechanics certificates produced by the decision path itself. Slice 10 adds independent evidence with separate implementation and worker provenance so a shared implementation defect cannot pass merely because the same code recomputes the same answer.

Two independent routes are required for publication-grade assurance:

1. **Reference mechanics reconciliation** — an in-process, dependency-free checker that consumes sealed core contracts only and independently reconstructs current-state legality, transfer resources, hits, chip availability, squad/XI/bench/captain structure and expected mechanics.
2. **Reference solver parity** — an external worker certificate bound to the exact `DecisionInputId`, `CandidateUniverseId` and `DecisionPolicyId`, admitted through a qualified worker registry and verified against immutable input/output/code artifacts.

A missing route is not success. Missing, limited, errored or unqualified external solver evidence remains `INCONCLUSIVE` and blocks publication-grade independent assurance.

## Independence boundary

`src/apex_fpl/assurance/reference_mechanics.py` is forbidden from importing `apex_fpl.decision.engine` or `apex_fpl.decision.mechanics`. Its autosub calculation deliberately uses a different exhaustive realised-appearance-state algorithm instead of the dynamic-programming weight calculation used by Slice 8.

The assurance path is also barred from V1 optimisation/services, network clients, runtime RNG, pandas/numpy/scipy and mutable live data. It receives sealed objects and immutable artifacts only.

This independence is an architectural property, not a comment: `tests/test_v2_assurance_architecture.py` fails if prohibited imports re-enter the path.

## Reference mechanics certificate

`ReferenceMechanicsCertificate` binds:

- `DecisionId` and `DecisionInputId`;
- exact `ManagerStateId`, `ForecastId`, `RuleSetId` and `CandidateUniverseId`;
- selected `action_id`;
- independently recomputed bank, hit points and `DecisionMechanics`;
- every mandatory check result exactly once;
- algorithm identity;
- retained source artifacts.

Mandatory checks cover input identity, current-exact state, owned/universe reconciliation, chip availability, transfer set and same-position rules, squad legality, realised-selling-resource finance, hit cost, XI legality, bench structure, captain/vice structure and expected mechanics.

A self-consistent but numerically tampered DecisionResult is therefore still detectable: the reference checker derives the mechanics from sealed forecast/state/rules instead of trusting the decision's arithmetic fields.

## External reference solver

`ReferenceSolverCertificate` is an untrusted worker statement until validated. It carries:

- exact decision input / universe / policy identities;
- worker name/version and code artifact;
- typed solver status;
- objective, bound and gap when available;
- selected action identity;
- action-surface completeness;
- tie-break policy identity when claimed;
- immutable solver input/output artifacts.

`ReferenceSolverRegistry` supplies authority. The registry starts with **no champion** in `config/reference_solvers_v2.yaml`. Publication-grade parity requires the certificate to match one registered `QUALIFIED` champion worker whose qualification/code artifacts verify and whose season/horizon validity covers the decision.

No worker is trusted merely because its file exists or because an older V1 workflow called it an independent solver.

## Solver authorization provenance

A runtime registry lookup is not sufficient historical proof by itself. When solver parity reaches PASS, Slice 10 creates a content-addressed `ReferenceSolverAuthorization` that binds the solver certificate to:

- the exact champion `ReferenceSolverWorkerId`;
- the worker code artifact;
- the empirical qualification artifact;
- the season, decision cutoff and horizon checked;
- an immutable registry artifact.

If the caller did not already retain registry bytes, Apex seals a canonical semantic snapshot of the exact registry object used for authorization. If retained registry bytes are supplied, they must reconstruct the same registry identity. The authorization artifact, registry artifact, code artifact and qualification artifact all become source lineage of the final assurance report.

## Parity semantics

For a feasible Apex decision:

- external `INFEASIBLE` is a contradiction and therefore `FAIL`;
- `ERROR`, `SOLVER_LIMIT` or merely `FEASIBLE` are `INCONCLUSIVE`;
- `OPTIMAL` must carry a complete zero-gap certificate;
- exact objective disagreement is `FAIL`, whether the reference optimum is higher or lower;
- if the worker claims the same tie-break policy, equal objective with a different selected action is also `FAIL`;
- exact objective parity, plus same-action parity when the same tie policy is claimed, is `PASS`.

Solver termination states are never collapsed. Absence is never converted to pass.

## Immutable replay

Mechanics certificates, solver certificates, solver authorization and the final `IndependentAssuranceReport` are content-addressed. Raw report replay reconstructs semantic objects, recomputes IDs, verifies referenced source artifacts and verifies certificate cross-links.

Publication-grade replay adds a stronger gate through `verify_stored_independent_assurance()`: a PASS-looking report must contain exactly one replayable solver authorization. Replay reopens the retained registry artifact, proves the same worker is still the recorded qualified champion for that historical authorization, and re-verifies the code and qualification artifacts. A PASS report with missing authorization, missing qualification evidence, a foreign registry, or inconsistent champion identity is rejected before it can enter the `AssuranceCase`.

A declared ID mismatch, missing worker/input/output/authorization evidence, malformed typed field or foreign certificate blocks replay.

## AssuranceCase integration

Slice 10 maps only **replay-verified** independent evidence into the constitutional `AssuranceCase`:

- successful reference mechanics -> `PO-MECHANICS-RECONCILIATION-001 = PROVEN`;
- failed reference mechanics -> `FAILED`;
- replay-verified qualified reference-solver parity PASS -> `PO-REFERENCE-SOLVER-PARITY-001 = PROVEN`;
- solver FAIL -> `FAILED`;
- absent/limited/unqualified/unverifiable solver evidence -> `INCONCLUSIVE`.

Both proof obligations are release-blocking. The existing ReleaseCertificate logic therefore cannot authorise publication because the main optimiser is confident while independent evidence is missing or contradictory.

## Deliberate non-claims

Slice 10 does not claim that an external reference solver is currently production-qualified. The default registry intentionally has no champion until qualification evidence exists. It also does not claim forecast/model correctness; it certifies decision legality/mechanics and independent optimisation parity for the exact sealed inputs it receives.

PR #66 remains archaeology and regression material only. Its legacy open-solver workflow, ad-hoc CSV interchange and float bench-weight configuration are not production authority in V2.
