# FPL Apex — Known Issues / Boundaries

Canonical machine authority: [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json). Operating authority: [`APEX_OPERATING_MANUAL.md`](APEX_OPERATING_MANUAL.md).

Apex V2 frozen engine SHA: `99cc7b51b0cff45462b567084cb1844cfe0a456f`. Canonical production workflow: `.github/workflows/apex-v2-daily-production.yml`. Sole serving provider: **AIrsenal** H1–H8.

## K001 — Private manager state is not public

Predeadline public FPL endpoints may not expose a manager's unpublished transfers/current private draft. Production therefore requires its authenticated private-manager state for entry 63984 and must fail closed rather than inventing a squad.

## K002 — Early-season forecast uncertainty

2026/27 minutes, tactical roles and attacking rates are still partly prior-driven while current-season evidence accumulates. This is forecast uncertainty, not permission to introduce a second hidden conservative selector.

## K003 — Market odds are not assumed serving inputs

Do not claim a betting-market feed is part of the frozen serving constitution unless a future certified engine explicitly says so. Optional research evidence cannot silently change production.

## K004 — Challenger evidence is non-serving

Apex Proprietary, Dastan, PITCHSIDE and OpenFPL remain shadow/diagnostic. Tournament and Decision Quality evidence can support review but cannot blend into AIrsenal, vote on the recommendation or trigger automatic promotion.

## K005 — Dastan horizon boundary

Dastan is H1-only. It may participate in H1 mechanics/availability research but cannot supply an invented pure-provider H2+ plan. Decision Quality must mark unsupported experiments absent rather than fabricate future forecasts.

## K006 — No-hindsight gaps are permanent gaps

A forecast or decision variant that was not immutably sealed before the relevant Official FPL deadline may not be reconstructed later. GW2 remains non-canonical diagnostic rehearsal. Postdeadline assembly may only package decisions that were already sealed predeadline.

## K007 — Decision Quality exact-task runtime

**Resolved operationally by PR #114; live GW3 acceptance remains the proof gate until the corrected run completes.**

The frozen transfer optimiser permits up to 17 MILP calls at 120 seconds each, or 34 minutes of solver allowance before orchestration. The prior 30-minute matrix timeout could not guarantee exact completion. The workflow now grants 50 minutes per independent solve task and `ops_tests/test_apex_v2_decision_lab_runtime_bound.py` derives the theoretical bound plus 15 minutes of headroom from the frozen source. Candidate depth, horizon, MIP gap and exact mechanics were not changed.

## K008 — Project Brain architecture drift

**Resolved and merged by PR #115 on 2 September 2026.** Canonical Project Brain, ChatGPT/operator and status documents now anchor to `APEX_V2_AUTHORITY.json`, the frozen engine SHA and the immutable V2 production path. Generic governance and the V2 Ops Contract fail if canonical authority documents revive obsolete V1/Pinnacle current-production claims.

## K009 — Generic governance preserved obsolete production

**Resolved and merged by PR #115 on 2 September 2026.** `scripts/check_governance_consistency.py` now validates the V2 authority manifest against the exact frozen `config/apex_v2.yaml`, recognizes exactly one serving production workflow and classifies the remaining active workflows as operations/research. The exact final PR head passed full pytest, Ruff, upstream consistency, generic governance and the V2 frozen-evaluator contract before merge.

## K010 — Legacy publishers retained executable write paths

**Resolved and merged by PR #115 on 2 September 2026.** Historical `pinnacle.yml`, `airsenal.yml`, `refresh-core-pin.yml` and `gw1-final-2026.yml` are preserved byte-for-byte under `archive/workflows/` and are absent from `.github/workflows`, making them inert forensic history. Governance and the V2 Ops Contract fail if they return to the executable workflow directory.

## K011 — Mutable historical evaluation reference

Some non-serving prospective evaluation paths have used `vaastav/Fantasy-Premier-League@master`. The branch existed at the last audit, so this is not a current serving fault, but deterministic evaluation should use the exact history commit pinned in `upstreams.lock.json` wherever the consumer supports it. Current OpenFPL readiness is a special case: it resolves the moving current-season history ref to a full immutable commit before reading rows and records that resolved commit, because freezing that monitor to an old baseline would prevent new completed Gameweeks from becoming observable.

## K012 — GitHub Actions Node runtime maintenance

Current workflows can emit warnings for action versions targeting Node 20 while GitHub runners force a newer runtime. This has not been a functional failure. Current upstream action releases provide Node 24-compatible generations; migrate them in a separate CI-proven maintenance PR rather than coupling runner maintenance to the GW3 decision-lab acceptance.

## K013 — External provider automation permissions

Fantasy Football Hub remains permission-required; FPL Review and FantaLens automation permission is not yet verified. Do not scrape or automate a provider without an acceptable permission/licence basis. This is research intake governance, not a serving blocker.

## K014 — AIrsenal setup team ID is intentionally not the production entry

AIrsenal's upstream database setup requires a positive FPL team ID, and the worker uses `1` only to satisfy that interface while skipping manager-specific transaction updates. It emits player forecasts. Apex separately authenticates production entry 63984. Changing the worker setup value to 63984 would conflate independent concerns and is not a fix.

## K015 — Football randomness remains irreducible

Apex can improve forecast calibration and decision quality; it cannot eliminate outcome variance. Diagnostic confidence, model agreement and realized decision edge must not be presented as certainty of a player return or rank outcome.

## Resolution discipline

Do not delete resolved issues. Mark them resolved with implementation, CI and live acceptance evidence. Durable limitations should remain visible even when they are non-serving or nonblocking.
