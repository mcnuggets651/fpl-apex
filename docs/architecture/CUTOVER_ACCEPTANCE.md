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
- [ ] Dastan/OpenFPL stay non-serving until current-scoring live exports pass the same contract.

## Team mechanics
- [ ] Exact legal 15/XI/club limits pass property tests.
- [ ] Rolled free-transfer transitions are versioned by season.
- [ ] Selling price uses purchase-price half-profit rules.
- [ ] Existing team value above £100m is not falsely declared illegal.
- [ ] Transfer cash flow and hit cost are exact.
- [ ] H1-only evidence withholds discretionary transfers.
- [ ] Incomplete selling-price state withholds discretionary transfers.
- [ ] Secondary tie-break prefers fewer transfers without reducing primary EV.

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
- [ ] Fresh AIrsenal generation succeeds.
- [ ] Official final anchor and snapshot freeze succeed.
- [ ] Solver completes from frozen state.
- [ ] Final release becomes immutable and verifies.
- [ ] Recommendation is legal and certification is coherent.
- [ ] After the GW, outcome/evaluation releases are produced.

Only after every applicable item is proven do we merge the cutover PR that retires V1 production writers/workflows.
