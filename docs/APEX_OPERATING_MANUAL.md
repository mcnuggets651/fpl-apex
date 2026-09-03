# FPL Apex — Operating Manual

**Authoritative human operating document for Apex V2.** Machine authority: [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json). If prose and the manifest disagree, stop and repair governance before acting.

## 1. Frozen operating constitution

- Season: 2026/27.
- Production FPL entry: 63984.
- Immutable PR #90 forensic/base SHA (`frozen_engine_sha`): `99cc7b51b0cff45462b567084cb1844cfe0a456f`.
- Frozen engine PR: #90.
- **NEVER merge or advance PR #90** as part of normal operations, research, documentation, incident repair or successor promotion.
- Serving-code pointer: `production_core_sha` in `APEX_V2_AUTHORITY.json`.
- `production_core_sha` must be an exact 40-character commit descended from the immutable PR #90 base and may move only through the certified successor/readiness/canary process.
- During the authority-split migration, `production_core_sha` intentionally remains `99cc7b51b0cff45462b567084cb1844cfe0a456f`; separating the fields itself changes no serving semantics.
- Control plane: `main`.
- Sole production workflow: `.github/workflows/apex-v2-daily-production.yml`.
- Sole serving provider: **AIrsenal**, H1–H8.
- All challengers/research: non-serving unless a future explicit certified constitution replaces this one.
- Research `production_influence = NONE`; no blending, voting, silent fallback or automatic promotion.

Official FPL is factual authority for identity, club, FPL position, price, status/availability and fixtures.

The immutable base and production core have different jobs. `frozen_engine_sha` preserves the exact clean-room lineage and non-serving evaluator reference. `production_core_sha` identifies the code that may serve production. Never overwrite the former to promote the latter.

## 2. Mandatory startup sequence

For any substantive Apex engineering or actionable FPL request:

1. Read `APEX_V2_AUTHORITY.json`.
2. Read `CURRENT_STATE.md` and `APEX_MASTER_CONTEXT.md`.
3. Read this manual.
4. Read `APEX_V2_DAILY_OPERATIONS.md` and the relevant V2 runbook.
5. Verify live GitHub `main` rather than trusting a stale handoff SHA.
6. Verify PR #90 is still open/draft/unmerged at the immutable `frozen_engine_sha`.
7. Verify `production_core_sha` is the intended serving core and is descended from `frozen_engine_sha`.
8. Inspect the relevant current workflow/release state and timestamps.
9. For an actionable recommendation, require exact authenticated manager state and a valid immutable serving final; never reconstruct a squad from memory.
10. Use external/live football research only for a concrete evidence gap such as injuries, transfers, roles or lineups, and do not let it bypass Official FPL identity or the serving contract.

Historical V1/Pinnacle files are evidence only. They are not a startup authority.

## 3. Production answer contract

Apex produces one canonical production recommendation. When the serving gate is healthy, report the production action and its evidence; when it is not healthy, report the blocker and withhold an invented Apex recommendation.

An actionable result must be bound to:

- exact manager state for entry 63984;
- immutable Official FPL/player/fixture authority;
- the exact `production_core_sha` that generated the run;
- immutable lineage back to `frozen_engine_sha` / PR #90;
- qualified serving AIrsenal H1–H8 forecasts;
- one frozen acquisition snapshot;
- legal optimisation and exact FPL mechanics;
- immutable publication identity.

The recommendation should expose, where relevant to the current Gameweek:

- transfers or roll;
- XI;
- captain;
- vice-captain;
- bench order;
- H2–H3 tactical plan;
- H4–H8 conditional scenarios;
- explicit blockers/risks.

Do not substitute a research counterfactual, a shadow-provider team, an old generated JSON file or an ad-hoc manually selected squad.

## 4. Production execution path

`.github/workflows/apex-v2-daily-production.yml` is the only serving production execution path. It must continue to:

1. check out exact `main` as the operations control plane;
2. read `production_core_sha` and `frozen_engine_sha` from `APEX_V2_AUTHORITY.json`;
3. prove the production core is descended from the immutable PR #90 base and materialize that exact core in a detached worktree;
4. install the selected core, using its exact dependency lock when supported;
5. use production-core-owned config, provider-worker scripts, upstream pins, acquisition, solve, mechanics and publication code for decision-driving behavior;
6. preflight the private immutable manager/release store;
7. authenticate and prove the exact configured manager;
8. create immutable attempt intent carrying the exact production-core SHA;
9. hash Official FPL authority before provider work;
10. produce/acquire governed provider surfaces;
11. re-anchor Official FPL and freeze inputs exactly once;
12. solve with network access disabled;
13. run production-core architecture/mechanics checks;
14. publish private prerequisites first and the immutable final last.

Operations controllers may come from exact `main` only where they are explicitly non-model orchestration. They must not replace production-core config/model/decision code. A workflow that cannot satisfy these invariants must fail closed rather than silently fall back.

## 5. Authentication boundary

Auth keepalive may rotate/repair durable owner credentials and verify manager identity. It cannot acquire providers, solve or publish a recommendation. Production and keepalive share a non-cancelling auth concurrency boundary so rotating credentials cannot be consumed concurrently.

Wrong-manager identity, failed private persistence, unexpected auth failures or exhausted recovery paths are hard failures. Do not turn direct credentials into a pseudo-keepalive success.

## 6. Provider constitution

AIrsenal is the sole serving champion H1–H8. Its upstream setup team ID `1` is an intentional database-initialisation placeholder; manager-specific transaction updates are skipped and Apex separately authenticates entry 63984. Do not "repair" that value to 63984.

Apex Proprietary, Dastan, PITCHSIDE and OpenFPL are shadow/diagnostic providers. Dastan is H1-only and therefore cannot be assigned an invented H2+ pure-provider plan. A missing or incomplete shadow can be recorded according to the production-core constitution but may not become a silent serving fallback.

## 7. EV-first evidence policy

The pre-solve production eligibility policy remains **adverse-evidence-only**.

Expected minutes, appearance/start probability, role uncertainty and confidence already influence projected points. Do not create a hidden second selector that automatically removes high-upside players merely because their minutes forecast is uncertain.

Hard exclusion/eligibility changes require current attributable adverse evidence such as:

- Official adverse availability/suspension status;
- decision-grade negative role or availability evidence;
- a material unresolved contradiction in current supported evidence.

Feed health is not player evidence. Tactical/availability/set-piece overrides require provenance, timing and appropriate expiry. Ordinal set-piece hierarchy must not be converted into invented literal future shares.

## 8. No-hindsight research law

Prospective tournament and Decision Quality research must seal forecasts/decisions before the Official FPL deadline.

Allowed after deadline:

- verify already immutable predeadline material;
- assemble/package a complete set of already sealed decisions;
- score outcomes once Official results exist;
- update diagnostic/review learning.

Forbidden after deadline:

- generate a missing forecast;
- reconstruct a missing counterfactual decision;
- change a sealed decision using outcome knowledge;
- canonicalise GW2 retrospectively;
- use research to mutate serving authority.

The prospective tournament/evaluation surface may remain bound to the immutable frozen evaluator for longitudinal comparability. That does not make `frozen_engine_sha` the serving production pointer and cannot promote a challenger automatically.

## 9. Decision Quality runtime contract

Parallel Decision Quality exists to preserve exact frozen-evaluator research semantics while removing serial wall-clock accumulation. A heavy task may call the frozen transfer-horizon optimiser once.

For the immutable evaluator lineage currently anchored at PR #90:

`(1 + 2 * candidate_limit) * per_MILP_time_limit`

with `candidate_limit = 8` and `per_MILP_time_limit = 120 seconds` gives 2040 seconds / 34 minutes of theoretical MILP allowance. The matrix solve job uses 50 minutes, including 15 minutes of explicit orchestration headroom. `ops_tests/test_apex_v2_decision_lab_runtime_bound.py` derives and enforces this against the frozen evaluator source.

Never reduce candidate depth, planning horizon, MIP precision or exact mechanics merely to make the lab fit a workflow timeout.

## 10. Production versus research communication

Always label these states separately:

- **Production** — immutable serving result from the authority-declared `production_core_sha` through Apex V2 Daily Production.
- **Operations** — auth, deadline dispatch and evaluation orchestration on `main` around the production core and frozen research evaluator.
- **Research/shadow** — prospective tournament, Decision Quality, provider diagnostics and learning; non-serving.
- **Historical** — V1/V1.5/Pinnacle workflows, generated files and old launch artifacts.

A green research workflow does not imply a new serving model. A poor football outcome does not justify changing serving authority. Diagnose factual input, forecast, mechanics and decision layers before proposing architecture change.

## 11. Code/change boundaries

Normal operations repair may modify bounded workflow/controller/governance/documentation code on `main` while model/source/config changes live on an independently reviewed successor branch.

Do not modify `src/`, `config/` or engine tests under the label of an operations repair. A genuine engine change requires explicit re-certification of a descendant successor SHA and deliberate `production_core_sha` migration. **It does not modify `frozen_engine_sha` or advance PR #90.**

Every non-trivial change should have:

- search/audit evidence;
- regression tests;
- Ruff/static checks as applicable;
- generic required CI (`test`, `contract`, `readiness`);
- Apex V2 Ops Contract when the operations surface is touched;
- exact final-head verification before merge;
- read-only successor readiness/canary proof before a production-core promotion;
- live runtime acceptance when private/live state is part of the contract;
- documentation/known-issue updates for durable changes.

## 12. Governance/anti-drift rules

The generic governance checker must read `APEX_V2_AUTHORITY.json` and independently enforce both identities:

- `frozen_engine_sha` is exactly the immutable PR #90 base `99cc7b51b0cff45462b567084cb1844cfe0a456f`;
- `production_core_sha` is a valid descendant commit used for serving production.

It must compare provider constitution/season/entry/horizon semantics with the **production-core** `config/apex_v2.yaml`, enforce exactly one serving production workflow, prove the production workflow resolves the production pointer and rejects a non-descendant core, and reject legacy executable publishers in `.github/workflows`.

Canonical authority docs must not revive obsolete claims that Pinnacle/V1 is current production, that `scripts/run_apex.py` is the current serving command, that an August GW1 squad is current, or that old direct-main publishers are live.

Retired executable workflows are preserved under `archive/workflows/` for forensics. Moving them there is a safety boundary: GitHub Actions does not execute workflow YAML outside `.github/workflows`.

## 13. Completion standard

A phase is not complete because code was written. Completion means the intended change is merged, all required CI is green on the exact head, read-only candidate readiness/canary proof is green before promotion, live/private runtime behavior is verified where relevant, immutable release identities are checked, frozen PR #90 is reverified and the Project Brain describes the same architecture as the runtime.
