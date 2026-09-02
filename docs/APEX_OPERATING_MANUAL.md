# FPL Apex — Operating Manual

**Authoritative human operating document for Apex V2.** Machine authority: [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json). If prose and the manifest disagree, stop and repair governance before acting.

## 1. Frozen operating constitution

- Season: 2026/27.
- Production FPL entry: 63984.
- Frozen certified engine SHA: `99cc7b51b0cff45462b567084cb1844cfe0a456f`.
- Frozen engine PR: #90.
- **NEVER merge or advance PR #90** as part of normal operations, research, documentation or incident repair.
- Control plane: `main`.
- Sole production workflow: `.github/workflows/apex-v2-daily-production.yml`.
- Sole serving provider: **AIrsenal**, H1–H8.
- All challengers/research: non-serving unless a future explicit certified constitution replaces this one.
- Research `production_influence = NONE`; no blending, voting, silent fallback or automatic promotion.

Official FPL is factual authority for identity, club, FPL position, price, status/availability and fixtures.

## 2. Mandatory startup sequence

For any substantive Apex engineering or actionable FPL request:

1. Read `APEX_V2_AUTHORITY.json`.
2. Read `CURRENT_STATE.md` and `APEX_MASTER_CONTEXT.md`.
3. Read this manual.
4. Read `APEX_V2_DAILY_OPERATIONS.md` and the relevant V2 runbook.
5. Verify live GitHub `main` rather than trusting a stale handoff SHA.
6. Verify PR #90 is still open/draft/unmerged at the frozen SHA.
7. Inspect the relevant current workflow/release state and timestamps.
8. For an actionable recommendation, require exact authenticated manager state and a valid immutable serving final; never reconstruct a squad from memory.
9. Use external/live football research only for a concrete evidence gap such as injuries, transfers, roles or lineups, and do not let it bypass Official FPL identity or the serving contract.

Historical V1/Pinnacle files are evidence only. They are not a startup authority.

## 3. Production answer contract

Apex produces one canonical production recommendation. When the serving gate is healthy, report the production action and its evidence; when it is not healthy, report the blocker and withhold an invented Apex recommendation.

An actionable result must be bound to:

- exact manager state for entry 63984;
- immutable Official FPL/player/fixture authority;
- the frozen engine SHA;
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

1. check out/prove `99cc7b51b0cff45462b567084cb1844cfe0a456f`;
2. preflight the private immutable manager/release store;
3. authenticate and prove the exact configured manager;
4. create immutable attempt intent;
5. hash Official FPL authority before provider work;
6. produce/acquire governed provider surfaces;
7. re-anchor Official FPL and freeze inputs exactly once;
8. solve with network access disabled;
9. run the frozen architecture/mechanics checks;
10. publish private prerequisites first and the immutable final last.

A workflow that cannot satisfy those invariants must fail closed rather than silently fall back.

## 5. Authentication boundary

Auth keepalive may rotate/repair durable owner credentials and verify manager identity. It cannot acquire providers, solve or publish a recommendation. Production and keepalive share a non-cancelling auth concurrency boundary so rotating credentials cannot be consumed concurrently.

Wrong-manager identity, failed private persistence, unexpected auth failures or exhausted recovery paths are hard failures. Do not turn direct credentials into a pseudo-keepalive success.

## 6. Provider constitution

AIrsenal is the sole serving champion H1–H8. Its upstream setup team ID `1` is an intentional database-initialisation placeholder; manager-specific transaction updates are skipped and Apex separately authenticates entry 63984. Do not "repair" that value to 63984.

Apex Proprietary, Dastan, PITCHSIDE and OpenFPL are shadow/diagnostic providers. Dastan is H1-only and therefore cannot be assigned an invented H2+ pure-provider plan. A missing or incomplete shadow can be recorded according to the frozen constitution but may not become a silent serving fallback.

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

## 9. Decision Quality runtime contract

Parallel Decision Quality exists to preserve exact frozen semantics while removing serial wall-clock accumulation. A heavy task may call the frozen transfer-horizon optimiser once.

For the current frozen engine:

`(1 + 2 * candidate_limit) * per_MILP_time_limit`

with `candidate_limit = 8` and `per_MILP_time_limit = 120 seconds` gives 2040 seconds / 34 minutes of theoretical MILP allowance. The matrix solve job uses 50 minutes, including 15 minutes of explicit orchestration headroom. `ops_tests/test_apex_v2_decision_lab_runtime_bound.py` derives and enforces this against frozen source.

Never reduce candidate depth, planning horizon, MIP precision or exact mechanics merely to make the lab fit a workflow timeout.

## 10. Production versus research communication

Always label these states separately:

- **Production** — immutable serving result from Apex V2 Daily Production.
- **Operations** — auth, deadline dispatch and evaluation orchestration around the frozen engine.
- **Research/shadow** — prospective tournament, Decision Quality, provider diagnostics and learning.
- **Historical** — V1/V1.5/Pinnacle workflows, generated files and old launch artifacts.

A green research workflow does not imply a new serving model. A poor football outcome does not justify changing the frozen constitution. Diagnose factual input, forecast, mechanics and decision layers before proposing architecture change.

## 11. Code/change boundaries

Normal operations repair may modify bounded workflow/controller/governance/documentation code on `main` while the root execution worktree remains frozen.

Do not modify `src/`, `config/` or frozen engine tests under the label of an operations repair. A genuine engine change requires explicit freeze-break/re-certification, a replacement certified SHA and deliberate production pin migration.

Every non-trivial change should have:

- search/audit evidence;
- regression tests;
- Ruff/static checks as applicable;
- generic required CI (`test`, `contract`, `readiness`);
- Apex V2 Ops Contract when the operations surface is touched;
- exact final-head verification before merge;
- live runtime acceptance when private/live state is part of the contract;
- documentation/known-issue updates for durable changes.

## 12. Governance/anti-drift rules

The generic governance checker must read `APEX_V2_AUTHORITY.json`, compare it with frozen `config/apex_v2.yaml`, enforce exactly one serving production workflow and reject legacy executable publishers in `.github/workflows`.

Canonical authority docs must not revive obsolete claims that Pinnacle/V1 is current production, that `scripts/run_apex.py` is the current serving command, that an August GW1 squad is current, or that old direct-main publishers are live.

Retired executable workflows are preserved under `archive/workflows/` for forensics. Moving them there is a safety boundary: GitHub Actions does not execute workflow YAML outside `.github/workflows`.

## 13. Completion standard

A phase is not complete because code was written. Completion means the intended change is merged, all required CI is green on the exact head, live/private runtime behavior is verified where relevant, immutable release identities are checked, frozen PR #90 is reverified and the Project Brain describes the same architecture as the runtime.
