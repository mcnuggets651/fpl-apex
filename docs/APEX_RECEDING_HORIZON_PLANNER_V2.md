# Apex V2 Exact Receding-Horizon Planner

## Purpose

The V2 production DecisionPolicy is not a one-Gameweek squad optimiser. Production authority requires a versioned receding-horizon decision whose objective is governed expected FPL value over the declared horizon while still exposing exactly one immediately executable current-Gameweek action.

This document defines the production semantics implemented on `v2/receding-horizon-planner`. It does not create or promote a production champion and it does not convert synthetic mechanism evidence into real qualification evidence.

## Tactical analysis is not production planning

The existing tactical `DecisionResult` remains a valid one-Gameweek analysis/reference object. It optimises exact current-Gameweek FPL mechanics and therefore may reject a lower-immediate-EV action even when that action has superior future value.

`RecedingHorizonDecisionResult` is a distinct contract. It may select a current action with lower immediate expected points when the exact governed horizon objective is higher. Tactical and receding results are intentionally not interchangeable.

## Hypothetical state is not current truth

Future branches use immutable `PlanningState` objects. A PlanningState is content-addressed and records the exact FPL-relevant squad, bank, free-transfer and chip-entitlement facts needed for hypothetical transition arithmetic, plus parent/action lineage.

A PlanningState never carries `CURRENT_EXACT` ManagerState authority. It cannot be used as proof of live manager truth and it cannot inherit current-state attestation merely because it was derived from a current ManagerState.

The retained root of every production planning result is the exact current `ManagerState`. Replay starts from those retained bytes and re-executes every selected or alternative transition.

## Exact transition mechanics

The planning transition layer uses the same governed FPL action surface as the tactical engine and preserves exact RuleSet mechanics:

- normal transfers use realised selling values and Official-current incoming prices;
- transfer finance is simultaneous and integer-tenths exact;
- paid transfers carry the exact governed hit cost;
- free transfers are consumed, granted and banked under the retained RuleSet cap;
- Wildcard transfers persist while their hit cost is zero under the governed chip rule;
- Free Hit creates a one-Gameweek temporary squad and the subsequent planning state reverts to the pre-Free-Hit permanent squad/finance state under the retained rules;
- Triple Captain and Bench Boost affect only the governed scoring surface;
- chip entitlement is set-aware and respects the retained first/second-set boundaries and disallowed Gameweeks.

Future prices are not guessed. Under the current certified price policy every hypothetical purchase uses the sealed Official-current price surface.

## Horizon objective

For a horizon of `H` Gameweeks the planner evaluates exact rational value from:

1. each Gameweek's exact FPL action objective;
2. the retained continuation weight for that horizon position; and
3. the terminal reserve value of still-unused chip entitlements after the final horizon transition.

The terminal reserve is option value, not already-earned FPL points. Expired entitlements contribute zero. Used entitlements cannot be valued again. A horizon crossing the seasonal chip-set boundary is evaluated from the exact set-aware hypothetical chip history.

All durable values use reduced exact rational arithmetic. No hidden floating tolerance decides a tie.

## Candidate surface and search claims

Production candidate policy is `FULL_OFFICIAL`. The planner does not call a hidden shortlist, arbitrary transfer cap or heuristic candidate truncation "exact".

The executable planner maintains a legal incumbent and uses only proof-valid bounds/dominance to discard branches. A node/resource limit is not infeasibility and is not optimality.

A certifying planning result requires:

- `PlanningSolverStatus.OPTIMAL`;
- `search_complete=true`;
- exact incumbent and best bound reconciliation;
- exact zero gap; and
- the selected trajectory/action to reconcile with the returned planning result identity.

If the full surface cannot be exhausted within the allowed work, the result remains `SOLVER_LIMIT` with a retained incumbent, bound and non-negative gap. Production bundle replay rejects it.

## Immutable planning replay

A stored planning result is not trusted because its JSON is internally consistent. Replay requires:

- the exact retained current ManagerState;
- the exact retained RuleSet;
- the exact CandidateUniverse;
- the exact continuation and chip-option support policies;
- every retained hypothetical PlanningState referenced by the result; and
- re-execution of every trajectory transition.

Each replayed state identity and each trajectory objective must reconcile. A missing, substituted or corrupted parent state/rules artifact fails closed.

## Robustness objective

Scenario robustness remains fixed-current-action/current-Gameweek football uncertainty. It does not pretend to simulate every future transfer branch.

However selection regret is anchored to the decision's governed selection objective:

- tactical results use current-Gameweek EV;
- receding results use the exact multi-Gameweek horizon objective.

This prevents robustness from falsely vetoing a legitimate future-value tradeoff merely because the selected root action has lower immediate xP.

## Independent planning reference solver

The tactical reference-solver contract remains frozen for historical/mechanism replay. Production receding-horizon parity uses the separate contract:

`apex-v2-exact-receding-horizon-parity-v2`

The planning worker does not import the main planner, planning-state transition implementation or production action-surface module. It independently reconstructs the declared planning transition/objective/search semantics while reusing only the already isolated reference-mechanics primitives.

A planning solver certificate is derived from retained request bytes, retained worker output and the exact worker code artifact. `OPTIMAL` requires complete zero-gap search and exact selected action + selected trajectory identity.

## Algorithmic worker qualification

A planning worker cannot become production-qualified merely because a code artifact exists or one happy-path unit test passes.

Qualification replays a sealed corpus against retained expected planning results and derives coverage from what the cases actually execute. The mandatory derived coverage includes:

- support-policy binding;
- full-Official action surface;
- multi-Gameweek objective;
- non-zero terminal chip reserve;
- actual free-transfer banking;
- actual transfer-finance surface;
- Triple Captain surface;
- Bench Boost surface;
- Wildcard persistence;
- Free Hit reversal;
- exact root-action parity;
- exact trajectory parity; and
- complete zero-gap search.

Coverage labels cannot be caller-authored. The controller derives them from retained request/result/run evidence. A missing category prevents qualification.

The worker registry remains fail-closed by exact solver contract. A tactical qualification cannot authorize a planning worker and a planning qualification cannot be replayed through an unknown contract.

## Production parity proof

`PO-REFERENCE-SOLVER-PARITY-001` is an algorithmic production proof, not empirical qualification.

For the receding-horizon production path, a satisfying claim must bind all of the following to the exact schema-v2 production planning bundle:

- exact `PlanningResultId`;
- replay-derived `PlanningReferenceSolverCertificate` identity;
- retained solver request/output and worker code;
- exact planning objective, root action and trajectory parity;
- replay-valid `ReferenceSolverAuthorization`;
- retained registry snapshot whose exact champion worker matches the certificate;
- replay-valid planning worker qualification covering the release season and horizon; and
- exact decision cutoff and tie-break policy.

A random algorithmic artifact, a valid certificate for another planning result, a limited/error run, an unqualified/non-champion worker or a certificate whose authorization is absent cannot satisfy production parity.

The same parity binding is replayed during publication authorization replay. It is therefore insufficient for the evidence to have been valid only when the release was first written.

## Schema-v2 production bundle

Authoritative production cutover accepts only `ProductionPlanningBundle` schema v2. The bundle binds the exact:

- current ManagerState and self-addressing artifact;
- RuleSet and self-addressing artifact;
- Forecast and exact ForecastModelArtifact;
- qualified receding-horizon DecisionPolicy and all four typed support policies;
- full-Official CandidateUniverse;
- complete zero-gap PlanningResult;
- ScenarioSet; and
- converged RobustnessReport.

Legacy schema-v1 tactical bundles remain replayable historical/mechanism evidence but cannot move the V2 production pointer.

## Deliberate non-claims

The mechanism tests use synthetic models, policies, scenarios, planning worlds, workers and backend doubles. They prove the contracts and failure modes only.

They do **not** prove that any real 2026/27 forecast model, DecisionPolicy, scenario system, learning policy, reference solver worker or durable backend is production-qualified.

`config/reference_solvers_v2.yaml`, `config/decision_policies_v2.yaml` and the other production champion registries remain fail-closed until genuine qualification evidence exists. Actual production cutover remains WITHHELD until all constitutional proof obligations are satisfied with real retained evidence.
