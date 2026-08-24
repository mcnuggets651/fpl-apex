# Apex V2 DecisionEngine — Slice 8 Contract

## Purpose

Slice 8 establishes the typed, replayable optimisation authority that consumes only sealed Apex V2 inputs. It does **not** claim that future football is certain, and it does **not** turn the current one-Gameweek reference optimiser into the production over-time strategy policy.

The governing production objective is expected FPL points over time. A tactical current-Gameweek solve is retained as a correctness/reference surface and is explicitly shadow-only.

## Sealed decision inputs

Every `DecisionInput` binds the semantic identities of:

- exact `ManagerStateId`;
- sealed `ForecastId`;
- active `RuleSetId`;
- immutable `CandidateUniverseId`;
- versioned `DecisionPolicyId`;
- gameweek and use mode;
- declared objective model;
- normal-transfer search limit;
- chip action surface; and
- numeric policy identity.

Changing the decision policy therefore changes the decision input identity even when the football data is unchanged.

No Slice 8 decision module has authority to fetch live data or read wall-clock time. Architecture tests block dependencies on V1 data/services/models, HTTP clients, dataframe runtimes and legacy optimiser authority.

## Exact ManagerState finance

Normal transfers use the currently owned player's **realised selling value** from exact ManagerState, not current market price and never a fresh £100m rebuild assumption.

Decision-critical money remains integer tenths. The transfer resource for an outgoing player is its `selling_price_tenths`; an incoming player costs the current Official price in the sealed candidate universe. Negative bank states are rejected.

Wildcard and Free Hit rebuilds use the same exact permanent-state financial basis. Free Hit returns the permanent bank after the temporary action.

Regression coverage includes:

- selling-resource affordability;
- hit double counting;
- zero-transfer/hold states;
- fresh-market-value in-season leakage; and
- Wildcard/Free Hit rebuild mechanics.

## Integrated submission mechanics

For each legal resulting squad, the reference mechanics exhaustively optimise the submitted FPL action rather than repairing it afterward.

Integrated variables include:

- legal XI and formation;
- captain;
- vice-captain;
- bench goalkeeper;
- ordered outfield bench;
- normal transfer count and hit cost;
- Triple Captain;
- Bench Boost;
- Wildcard; and
- Free Hit.

Bench value is derived from appearance probabilities, autosub order and legal formation preservation. There is no authoritative flat bench weight. Captain/vice value is likewise computed inside the submission objective, including vice fallback under the declared marginal appearance model.

The current reference evaluator uses exact rational arithmetic. Its numeric error bound is therefore zero for the arithmetic it performs.

## Forecast semantics used by the reference engine

Slice 8 consumes unconditional expected FPL points and forecast appearance distributions already compiled by Slice 7 under the sealed RuleSet.

For multiple fixtures in one Gameweek, gameweek appearance probability currently uses the declared marginal-independence baseline when combining fixture no-appearance probabilities. This assumption is named in `DecisionObjectiveModel.MARGINAL_INDEPENDENCE_BASELINE` and is **not** presented as correlation-aware truth.

Slice 9 owns correlated scenario robustness and convergence testing.

## Solver status

Solver termination state is typed and cannot be laundered:

- `OPTIMAL`
- `FEASIBLE`
- `INFEASIBLE`
- `UNBOUNDED`
- `SOLVER_LIMIT`
- `ERROR`
- `INVALID_INPUT`

`DecisionSearchOutcome` represents either a feasible `DecisionResult` or a typed failure. A timeout, worker error or solver limit can never become `INFEASIBLE` merely because no final optimum was returned.

The exhaustive Slice 8 reference implementation returns an exact `OPTIMAL` solver certificate over the **declared** action surface it actually enumerates, with incumbent, best bound, zero gap and zero arithmetic error bound. That does not by itself imply global production exactness.

## ExactnessClaim

Exactness is separately typed:

- `GLOBAL_OPTIMAL`
- `EPSILON_GLOBAL_OPTIMAL`
- `OPTIMAL_WITHIN_CERTIFIED_UNIVERSE`
- `FEASIBLE_INCUMBENT`
- `INCONCLUSIVE`

The claim records:

- candidate universe identity and scope;
- solver status;
- action-surface completeness;
- search completeness;
- best bound;
- gap;
- candidate filter identity;
- expansion result/certificate;
- numeric error bound; and
- limiting reasons.

A solver saying `OPTIMAL` over a scoped or incomplete action surface therefore cannot silently become a global-optimality claim.

## Candidate universe and expansion

`FULL_OFFICIAL` means every current Official player in the sealed world is present. `SCOPED` means a strict subset is used.

Every scoped universe must carry an immutable content-addressed prefilter artifact. The filter is part of candidate-universe identity and lineage.

A scoped result may be promoted to `OPTIMAL_WITHIN_CERTIFIED_UNIVERSE` only when a strict expanded solve:

1. uses the same GlobalWorld;
2. uses an identical ManagerState, Forecast, RuleSet, DecisionPolicy, numeric policy and action surface;
3. is a strict candidate superset;
4. reaches `FULL_OFFICIAL`;
5. is itself `GLOBAL_OPTIMAL`;
6. cannot have a worse optimum than the strict-subset baseline; and
7. produces no objective improvement above the explicit materiality threshold.

The expansion certificate recomputes `expanded_objective - baseline_objective` exactly and derives its result from that delta and the materiality threshold. A stored label that disagrees with the arithmetic is invalid even when the surrounding artifact bytes are content-addressed correctly.

If expansion finds a material improvement, the result is `MATERIAL_IMPROVEMENT_FOUND`; the narrow result stays unpromoted and the event is treated as a search-defect signal.

## DecisionPolicy and production boundary

Decision policy is an empirically qualifiable object, not a hidden collection of optimiser constants.

A policy versions:

- evaluation mode;
- objective policy;
- horizon;
- continuation/terminal value evidence;
- chip future-option-value evidence;
- price policy;
- candidate policy; and
- tie breaking.

The tactical reference engine implements one named deterministic tie policy: `lexicographic-official-id-v1`. A tactical `DecisionPolicy` requesting any other tie semantics is rejected rather than being hashed into identity and then silently ignored.

`TACTICAL_CURRENT_GAMEWEEK` is constitutionally exact about its scope: its horizon is exactly one Gameweek and it cannot carry continuation-value, chip-option-value, price-policy or candidate-policy artifacts that this endpoint does not execute. This prevents unused policy semantics from entering `DecisionPolicyId` while the engine silently behaves as if they did not exist.

A production-qualified policy must be:

- `QUALIFIED`;
- `RECEDING_HORIZON_WITH_CONTINUATION`;
- horizon >= 2;
- backed by a qualification artifact;
- backed by continuation-value evidence;
- backed by chip-option-value evidence;
- backed by price-policy evidence; and
- backed by candidate-policy evidence.

It must also be the registered champion for the season and every retained artifact must verify in ArtifactStore.

`config/decision_policies_v2.yaml` intentionally has no champion today. Apex does not fabricate horizon, terminal value, chip option value, price forecasts or candidate policy merely to open a production path.

The current `optimise_current_gameweek()` reference engine accepts only `TACTICAL_CURRENT_GAMEWEEK` policy and refuses `PRODUCTION` mode. This prevents a one-Gameweek endpoint from burning a long-lived chip or persistent transfer and then being mislabeled max-EV-over-time.

Empirical DecisionPolicy promotion belongs to later learning/replay qualification work.

## Immutable replay

Candidate universes and DecisionResults can be stored in ArtifactStore and replayed without network access.

Replay reconstructs strict typed contracts and recomputes semantic IDs. Corruption, declared-ID mismatch and type laundering fail closed. DecisionPolicyId is retained inside DecisionInput, so artifacts from different policy generations cannot collide or be compared as if they represented the same decision problem.

## Differential and adversarial tests

Slice 8 includes:

- an independent small-universe brute-force XI/captain oracle that does not call Slice 8 mechanics;
- exact free-transfer and hit-cost regressions;
- zero-transfer hold regression;
- tie/churn stability regression;
- exact selling-resource affordability regression;
- negative expected-points preservation;
- Wildcard and Free Hit rebuild regressions;
- Triple Captain and Bench Boost action-surface regressions;
- integrated bench/captain/vice regression;
- cached-versus-recomputed autosub-weight equivalence;
- candidate expansion success, forged-result and monotonicity regressions;
- solver-limit/error/infeasibility separation;
- rational numeric normalization; and
- decision replay integrity/type-laundering regressions.

These are reference/differential checks for Slice 8. Slice 10 still owns an operationally independent publish-time primal and mechanics verifier.

## Slice boundary and remaining gates

Slice 8 deliberately does **not** claim the full Apex production route is complete.

Remaining architecture responsibilities include:

- **Slice 9:** correlated scenarios, robustness and governed convergence;
- **Slice 10:** independent primal legality, transition and mechanics assurance;
- **Slice 11:** replay/learning/model and DecisionPolicy empirical qualification;
- **Slice 12:** V2 shadow production;
- **Slice 13:** explicit production cutover; and
- **Slice 14:** legacy production-authority removal after rollback window.

A green Slice 8 proves its software contracts and reference optimisation semantics. It does not imply `ready_to_act=true`, `safe_to_act=true`, a qualified forecast champion, a qualified DecisionPolicy champion or a current production recommendation.

## PR #66 migration boundary

PR #66 remains reference/archaeology/regression/model-research material. Slice 8 retains confirmed lessons such as solver-status integrity, exact in-season finance, candidate-expansion auditing, hit accounting and integrated mechanics, but does not import V1 optimisation as authority.
