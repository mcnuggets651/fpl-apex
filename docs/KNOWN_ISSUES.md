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

**Resolved operationally by PR #114 and accepted live on 2 September 2026.**

The frozen transfer optimiser permits up to 17 MILP calls at 120 seconds each, or 34 minutes of solver allowance before orchestration. The prior 30-minute matrix timeout could not guarantee exact completion. The workflow now grants 50 minutes per independent solve task and `ops_tests/test_apex_v2_decision_lab_runtime_bound.py` derives the theoretical bound plus 15 minutes of headroom from the frozen source. Candidate depth, horizon, MIP gap and exact mechanics were not changed.

Corrected Decision Quality run #10 (`33643925982`) completed successfully with all 8/8 fresh GW3 tasks sealed, including exact baseline reproduction and the previously timing-out Apex Proprietary availability overlay. Canonical assembly produced immutable private lab `apex-v2/private-decision-lab/2026-2027/33590896695-1`; all constituent decisions were already sealed before the GW3 deadline. This is the runtime acceptance proof. Keep the bound regression, but do not carry K007 as an open blocker.

## K008 — Project Brain architecture drift

**Resolved and merged by PR #115 on 2 September 2026.** Canonical Project Brain, ChatGPT/operator and status documents now anchor to `APEX_V2_AUTHORITY.json`, the frozen engine SHA and the immutable V2 production path. Generic governance and the V2 Ops Contract fail if canonical authority documents revive obsolete V1/Pinnacle current-production claims.

## K009 — Generic governance preserved obsolete production

**Resolved and merged by PR #115 on 2 September 2026.** `scripts/check_governance_consistency.py` now validates the V2 authority manifest against the exact frozen `config/apex_v2.yaml`, recognizes exactly one serving production workflow and classifies the remaining active workflows as operations/research. The exact final PR head passed full pytest, Ruff, upstream consistency, generic governance and the V2 frozen-evaluator contract before merge.

## K010 — Legacy publishers retained executable write paths

**Resolved and merged by PR #115 on 2 September 2026.** Historical `pinnacle.yml`, `airsenal.yml`, `refresh-core-pin.yml` and `gw1-final-2026.yml` are preserved byte-for-byte under `archive/workflows/` and are absent from `.github/workflows`, making them inert forensic history. Governance and the V2 Ops Contract fail if they return to the executable workflow directory. The operations change-surface contract also rejects future modification of `archive/workflows/**`, preserving that evidence after cutover.

## K011 — Mutable historical evaluation reference

**Audited; current OpenFPL usage is intentional and safe within its non-serving boundary.**

Some prospective evaluation paths observe `vaastav/Fantasy-Premier-League@master` because current-season completed Gameweeks must continue becoming visible. `openfpl_readiness()` does not consume that mutable ref directly: it resolves the supplied ref to a full 40-character commit SHA, then reads the current-season history directory at that exact immutable SHA and records `observed_history_commit`, commit time and a manifest digest. Freezing this monitor to the older baseline in `upstreams.lock.json` would prevent later completed Gameweeks from becoming observable.

Any different historical consumer that does not first resolve and record an immutable commit remains subject to the normal pinning rule. This exception grants no serving influence or model promotion authority.

## K012 — GitHub Actions Node runtime maintenance

**Resolved in the final 2 September 2026 operations closure.**

All executable workflows now use exact commit pins for the current certified Node-24-native GitHub-owned action generations:

- `actions/checkout` v7.0.1 — `3d3c42e5aac5ba805825da76410c181273ba90b1`;
- `actions/setup-python` v7.0.0 — `5fda3b95a4ea91299a34e894583c3862153e4b97`;
- `actions/cache` v6.1.0 — `55cc8345863c7cc4c66a329aec7e433d2d1c52a9`;
- `actions/upload-artifact` v7.0.1 — `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`.

`ops_tests/test_github_actions_runtime_contract.py` rejects stale mutable major references, unknown GitHub-owned actions and drift from the certified exact pins. `.github/dependabot.yml` checks GitHub Actions weekly and routes future updates through protected PR review instead of silently moving runtime dependencies. Archived forensic workflows are deliberately excluded from migration and are immutable under the V2 Ops Contract.

## K013 — External provider automation permissions

Fantasy Football Hub remains permission-required; FPL Review and FantaLens automation permission is not yet verified. Do not scrape or automate a provider without an acceptable permission/licence basis. This is research intake governance, not a serving blocker.

## K014 — AIrsenal setup team ID is intentionally not the production entry

AIrsenal's upstream database setup requires a positive FPL team ID, and the worker uses `1` only to satisfy that interface while skipping manager-specific transaction updates. It emits player forecasts. Apex separately authenticates production entry 63984. Changing the worker setup value to 63984 would conflate independent concerns and is not a fix.

## K015 — Football randomness remains irreducible

Apex can improve forecast calibration and decision quality; it cannot eliminate outcome variance. Diagnostic confidence, model agreement and realized decision edge must not be presented as certainty of a player return or rank outcome.

## K016 — Direct-owner credential diagnostic is not production auth health

The repository may contain a directly supplied FPL bearer/cookie that expires independently of the managed encrypted refresh state. A failure of `.github/workflows/apex-v2-direct-auth-diagnostic.yml` therefore means exactly that the direct credential failed its frozen owner preflight; it does **not** by itself prove that the managed keepalive/production authentication chain is unhealthy.

The direct-auth workflow is incident-only and manual `workflow_dispatch` only. Automatic `push`, `schedule` and `workflow_run` triggers are prohibited, refresh-token state is deliberately blanked, and it has no acquire/solve/publish/write authority. `ops_tests/test_github_actions_runtime_contract.py` locks this boundary. Managed auth health is established through the keepalive/production refresh path and exact manager-identity proof.

## Resolution discipline

Do not delete resolved issues. Mark them resolved with implementation, CI and live acceptance evidence. Durable limitations should remain visible even when they are non-serving or nonblocking.
