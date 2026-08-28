# Apex V2 Cutover Acceptance

Cutover is a binary governance event. A green unit test suite alone is insufficient.

## Repository controls
- [ ] `main` is protected by branch/ruleset controls; force-push and deletion are disabled.
- [ ] Apex V2 CI is a required check for production-code changes.
- [ ] GitHub **Release immutability** is enabled for the repository before the first production V2 release.
- [ ] Production and evaluation workflows have only the permissions they need.

## Architecture controls
- [ ] `python scripts/check_v2_architecture.py` passes.
- [ ] No `src/apex` import of `apex_fpl` exists.
- [ ] Decision code cannot import network/source modules.
- [ ] Shadows cannot be represented in production decision inputs.
- [ ] No automatic provider promotion or production ensemble exists.

## Official truth and provider contract
- [ ] Duplicate/unknown Official IDs fail.
- [ ] Price/position/team facts come only from Official FPL.
- [ ] `NO_FORECAST` never counts as coverage.
- [ ] Missing H1 coverage blocks serving.
- [ ] Provider timestamps and run-attempt freshness are checked.
- [ ] AIrsenal export is regenerated during the attempt.
- [ ] A canonical Official FPL hash is captured immediately before provider generation.
- [ ] The final Official FPL hash is reacquired before freeze and must exactly match the pre-provider hash.
- [ ] An Official-hash mismatch aborts before team/provider qualification and requires a new run attempt.
- [ ] Both Official acquisition hashes are persisted in the frozen run provenance.
- [ ] Dastan is generated before the shared freeze in an isolated runtime and remains non-serving while prospectively unqualified.
- [ ] OpenFPL's exact pinned reference checkout passes its structural preflight without being relabelled as current scoring.
- [ ] OpenFPL exact 2026/27 history readiness is pinned and audited independently of the Dastan history role; target/future GW contamination fails closed.
- [ ] Apex does not invent an OpenFPL current-training sample threshold. A governed training-policy version must explicitly set the minimum exact-rule history before model construction can be considered ready.
- [ ] Any future OpenFPL current model declares `fpl-2026-27-v1`, binds to that governed training policy, declares the exact-rule gameweeks used, meets its minimum, uses separately hashed training/model artifacts, trains only through GW < target GW, proves future-placeholder invariance, reaches 100% Official DecisionUniverse coverage, and explicitly does not reuse legacy reference weights as current weights.
- [ ] Dastan/OpenFPL stay non-serving until current-scoring live exports pass the same operational and prospective contract.

## Team mechanics
- [ ] Exact legal 15/XI/club limits pass property tests.
- [ ] Rolled free-transfer transitions are versioned by season.
- [ ] Current-period free-transfer state supports 0 through the season maximum; a new transfer with 0 remaining FTs incurs the first hit correctly.
- [ ] Selling price uses purchase-price half-profit rules.
- [ ] Existing team value above £100m is not falsely declared illegal.
- [ ] Transfer cash flow and hit cost are exact.
- [ ] Authenticated Official `/me/` must identify the configured Apex entry before `/my-team/{entry_id}/` can be trusted.
- [ ] Authenticated `/my-team/{entry_id}/` must provide 15 unique Official IDs, all purchase/selling prices, current bank and coherent transfer state.
- [ ] Every authenticated selling price is cross-checked against purchase price, the frozen Official current price and the exact half-profit rule.
- [ ] Team-state credentials are injected only during Official acquisition/freeze and are never logged, persisted in snapshots or exposed to forecast/solve code.
- [ ] A configured but rejected/wrong-entry/incoherent credential fails acquisition; Apex does not silently downgrade to public picks.
- [ ] With no credential, public last-deadline picks remain transaction-incomplete unconditionally and discretionary transfers are withheld.
- [ ] Unlimited/null-limit authenticated transfer windows are withheld from the ordinary transfer optimiser until chip-aware mechanics are explicitly implemented.
- [ ] H1-only evidence withholds discretionary transfers.
- [ ] Incomplete selling-price state withholds discretionary transfers.
- [ ] Execution overlays update squad, bank, owned purchase/selling-price maps and remaining current-period FTs atomically.
- [ ] Secondary tie-break prefers fewer transfers without reducing primary EV.
- [ ] Transfer optimiser infeasibility is returned as typed `INFEASIBLE`, persisted in the DecisionBundle diagnostics, and certifies fail-closed as `BLOCKED` / `DECISION_ILLEGAL` rather than surfacing as an unhandled exception.

## Snapshot/persistence
- [ ] Intent release is created before external acquisition.
- [ ] All decision inputs are frozen once.
- [ ] Post-freeze input mutation fails integrity checks.
- [ ] Solve phase uses only frozen files.
- [ ] Final attempt release is published even when certification is BLOCKED.
- [ ] Orphaned intent is detected after the grace period.
- [ ] Bundle/asset hashes are verified.
- [ ] Native immutable-release status is verified during cutover.

## Evaluation
- [ ] Outcomes are collected only after Official FPL marks the GW finished.
- [ ] Forecasts are evaluated from the frozen pre-deadline release, never regenerated.
- [ ] Metrics are player-gameweek grain.
- [ ] All-player and 60+ minute cohorts are reported.
- [ ] Evaluation releases cannot change provider authority.

## Live dress rehearsal
- [ ] One genuine pre-deadline V2 intent is published.
- [ ] Official pre-provider seal succeeds.
- [ ] Fresh AIrsenal generation succeeds.
- [ ] Optional challenger generation occurs before freeze and cannot invalidate the serving incumbent merely by failing.
- [ ] Official post-provider seal exactly matches the pre-provider seal.
- [ ] Official final anchor and snapshot freeze succeed.
- [ ] If authenticated team-state credentials are configured, the frozen team state is current, exact and complete for ordinary transfers; otherwise the diagnostic explicitly withholds discretionary transfers.
- [ ] Solver completes from frozen state or emits a typed/persisted blocking decision diagnostic.
- [ ] Final release becomes immutable and verifies.
- [ ] Recommendation is legal and certification is coherent.
- [ ] After the GW, outcome/evaluation releases are produced.

Only after every applicable item is proven do we merge the cutover PR that retires V1 production writers/workflows.
