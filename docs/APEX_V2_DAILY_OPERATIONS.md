# Apex V2 Daily Operations

## Purpose

Apex V2 core engineering is frozen at:

`99cc7b51b0cff45462b567084cb1844cfe0a456f`

Daily operation must not move that code pin implicitly. The default branch owns only the scheduling/orchestration layer; every production, authentication keepalive and evaluation run explicitly checks out the certified frozen SHA before installing or executing Apex V2.

This separates two concerns:

1. **Frozen engine** — model/provider constitution, optimizer, FPL mechanics, acquisition/privacy contracts and publication code.
2. **Operations layer** — when the frozen engine runs, bounded authentication recovery, immutable-attempt classification and how failures/evaluations are surfaced.

Changing the schedule or an operations controller does not change the engine. Changing the engine requires a new certified SHA and a deliberate pin update after production proof.

## Operations control-plane isolation

The daily workflows intentionally check out the frozen engine SHA as the root worktree. The two small operations controllers live on `main`:

- `scripts/apex_v2_auth_ops.py`
- `scripts/apex_v2_attempt_audit_ops.py`

A scheduled/manual workflow may not replace the frozen checkout with `main`. Instead it fetches the exact GitHub event SHA, extracts the required controller with `git show` into `$RUNNER_TEMP`, and immediately re-proves that root `HEAD` is still the frozen SHA. This keeps orchestration repairable without creating a second mutable model/decision implementation.

The operations contract CI unit-tests these controllers and rejects any repair PR that modifies `src/`, `config/` or the frozen `tests/` tree.

## Active daily lifecycle

### 0. Owner-auth keepalive — every six hours

Workflow: `.github/workflows/apex-v2-auth-keepalive.yml`

Schedule: `00:22`, `06:22`, `12:22`, `18:22` UTC.

The keepalive exists because Official FPL now uses a rotating PingOne OIDC refresh-token grant. A credential can be consumed, rotated or invalidated independently of the daily model schedule, so relying on a single refresh exchange once per day is not a robust operational assumption.

The keepalive:

1. checks out and proves the exact frozen Apex SHA;
2. preflights the separate immutable private auth store;
3. materializes the exact `main` auth controller into `$RUNNER_TEMP` without changing the frozen worktree;
4. invokes the frozen `scripts/preflight_fpl_auth.py` refresh/identity/persistence boundary;
5. verifies the credential belongs to the configured manager entry;
6. persists any newly rotated refresh token before the temporary access token can escape the auth boundary;
7. exits without creating an intent, fetching providers, solving, publishing a decision or changing any model state;
8. proves the frozen worktree stayed clean.

The keepalive and daily production share the non-cancelling concurrency group `apex-v2-fpl-auth`. They therefore cannot consume the same rotating token concurrently.

Keepalive **never** substitutes a direct bearer/cookie credential for a dead refresh chain. Its job is to maintain or repair the durable refresh chain; if that cannot be done it fails loudly.

### 1. Production — 04:17 UTC every day

Workflow: `.github/workflows/apex-v2-daily-production.yml`

The job:

1. checks out the exact frozen Apex V2 SHA;
2. proves `HEAD` equals that SHA;
3. validates the separate immutable private manager store when authenticated mode is enabled;
4. validates/rotates or safely recovers the FPL owner credential before provider work;
5. creates the immutable attempt intent;
6. captures the Official FPL pre-provider authority hash;
7. generates a fresh AIrsenal H1-H8 candidate from the pinned AIrsenal upstream;
8. generates Dastan as an isolated best-effort shadow;
9. performs the V2 acquisition stage, including the other governed shadow/diagnostic providers, then re-anchors Official FPL and freezes the inputs once;
10. uses the explicit atomic `--snapshot-output` machine handoff introduced by the Production #40 permanent repair;
11. solves with `APEX_ALLOW_NETWORK_DURING_SOLVE=0` and the architecture check enabled;
12. publishes private prerequisites first and then the immutable public completed attempt;
13. uploads sanitized diagnostics only.

Production shares `apex-v2-fpl-auth` concurrency with keepalive and keeps cancellation disabled. A slow production run is never silently replaced, and no keepalive can rotate its token underneath it.

Maximum workflow runtime remains 120 minutes, matching the certified production contract.

#### Bounded production authentication recovery

The normal path is unchanged: the frozen preflight loads the newest encrypted private refresh state, exchanges it, proves `/me/` belongs to the configured FPL entry and persists the rotated replacement before continuing.

Recovery is entered **only** when the frozen preflight emits the exact classified error `Official FPL refresh credential was rejected or expired`. Wrong-manager, private-store, decryption, unexpected HTTP, persistence and all other failures remain hard failures.

The recovery ladder is:

1. **Primary private rotating state** — unchanged frozen path.
2. **Bootstrap refresh re-seed** — if primary state is explicitly rejected, the configured `FPL_REFRESH_TOKEN` secret is tried directly through the frozen exchange, exact manager-identity proof and private persistence functions. This deliberately bypasses dead private state so a newly re-seeded bootstrap secret can heal the chain. The newly rotated token must be persisted before production may continue.
3. **Direct owner credential for this production run only** — only if both refresh grants are explicitly rejected may production ask the frozen preflight to independently verify the configured bearer/cookie against `/me/`. This does not repair the refresh chain and is therefore not available to keepalive.

If a bootstrap exchange succeeds but manager verification or persistence fails, production stops immediately. It does **not** mask a possibly consumed/rotated token by falling through to direct authentication.

If Official FPL has invalidated the private refresh state, the bootstrap refresh secret **and** every configured direct credential, automation cannot manufacture a new Premier League login. A fresh browser-issued OIDC refresh token must be placed in the `FPL_REFRESH_TOKEN` repository secret once. The next keepalive/production run will then use the explicit bootstrap-recovery path, verify the configured entry and re-establish encrypted private rotation. No engine change or re-rehearsal is required.

### 2. Evaluation — 06:41 UTC every day

Workflow: `.github/workflows/apex-v2-daily-evaluation.yml`

The evaluation is intentionally later than production. The normal gap is 2h24m; even a production run that reaches its 120-minute hard limit has a 24-minute separation before the scheduled evaluator begins.

The evaluator:

1. checks out and proves the same frozen SHA;
2. runs the frozen immutable intent/final audit and classifies missing finals through the operations acknowledgement policy;
3. preflights the private provider-evaluation store;
4. prospectively scores any newly completed Official FPL Gameweeks from the sealed pre-deadline provider surfaces;
5. rebuilds champion-challenger season standings;
6. uploads the derived standings artifact.

`evaluate-completed` is the lifecycle gate: if no new Official FPL Gameweek is complete, there is nothing to score. We do not fabricate outcomes or backfill forecasts after the deadline.

## Immutable failed-attempt acknowledgement policy

An intent without a matching final remains a serious production signal. The repair does **not** delete old intent releases, synthesize finals, change frozen `audit-attempts`, or globally ignore missing finals.

Before this policy was introduced, six PR-era production attempts were individually checked against their GitHub Actions run records and proven to have completed with `conclusion=failure`:

- `apex-v2/intent/2026-2027/33242604422-1`
- `apex-v2/intent/2026-2027/33257608630-1`
- `apex-v2/intent/2026-2027/33260512411-1`
- `apex-v2/intent/2026-2027/33265747805-1`
- `apex-v2/intent/2026-2027/33272866621-1`
- `apex-v2/intent/2026-2027/33312221205-1` (Production #40, subsequently fixed and superseded by successful #41)

Those exact immutable tags are acknowledged historical failures. They remain visible in the frozen audit output and are reported separately as `acknowledged_historical_failures`.

**Any other missing final is unacknowledged and hard-fails daily evaluation.** The acknowledgement set is code-reviewed, regression-tested and machine-checked by the ops contract. This turns the audit from a permanent historical red light into the intended detector for *new* operational failures without rewriting history.

## Single canonical publisher

The following legacy workflows remain on the default branch only as **manual-only compatibility/forensic workflows**:

- `.github/workflows/pinnacle.yml` (`Apex Unified`)
- `.github/workflows/airsenal.yml` (standalone legacy AIrsenal worker)
- `.github/workflows/refresh-core-pin.yml` (legacy mutable Core-pin refresher)

Their old `schedule` triggers are removed, and `Apex Unified` also loses its automatic `push` trigger. Each keeps only `workflow_dispatch` so the existing legacy contract/governance tests can continue to validate those historical paths without letting them execute automatically. Their first line is an explicit `RETIRED: manual-only legacy workflow` marker.

This guarantees one automated operational decision publisher: **Apex V2 Daily Production**. Auth keepalive publishes no decision and evaluation only scores sealed prospective surfaces. AIrsenal remains the sole V2 serving provider H1-H8; challengers remain sealed/nonserving unless the formal promotion policy is satisfied.

## Why the old Core-pin refresher is retired

Apex V2 Proprietary does not trust a mutable pin written to the default branch. The certified proprietary worker resolves the current Core `main` revision during acquisition, rejects stale Core according to the frozen freshness policy, freezes the accepted revision into the run-local provenance chain and rejects source drift. Keeping the old six-hour repository pin writer would add mutation/noise without improving V2 truth. The legacy workflow remains manually invokable only for forensic/backward-compatibility purposes.

## Failure behavior

Daily automation is fail-closed.

- Authentication/private-store failure outside the explicitly classified recovery ladder: production fails before intent/provider work or publication.
- Dead refresh chain during keepalive: keepalive fails; it cannot become a direct-auth pseudo-success.
- Wrong manager identity at any authentication path: hard failure.
- Successful refresh exchange followed by persistence failure: hard failure before the access token is used.
- Official pre/post hash disagreement: acquisition fails; no decision is published.
- Missing/invalid snapshot handoff: production fails before solve.
- Solve failure after intent: final publication fails and the orphan is surfaced as unacknowledged until deliberately investigated.
- New/unacknowledged missing final: evaluation hard-fails.
- Explicitly acknowledged historical failed intent: retained and reported, but does not permanently stop prospective scoring.
- Serving-provider qualification failure: certification withholds action rather than silently blending/falling back.
- Optional shadow/diagnostic failure: recorded according to the frozen provider constitution; it cannot become serving output.
- Evaluation failure: does not modify the already sealed pre-deadline attempt; the next evaluation run may retry prospectively from immutable inputs.

## Schedule contract CI

Workflow: `.github/workflows/apex-v2-ops-contract.yml`

The operations PR is rejected if it:

- modifies `src/`, `config/`, the frozen `tests/` tree or any non-allowlisted operations path;
- changes or removes the frozen SHA pin accidentally;
- removes the daily production/evaluation schedules or six-hour auth keepalive;
- lets keepalive call intent/provider/acquisition/solve/publish behavior;
- passes direct bearer/cookie secrets into keepalive;
- allows production and keepalive to rotate refresh state concurrently;
- weakens the exact-manager identity proof or persistence-before-use recovery invariant;
- changes the historical acknowledgement set without updating the tested operations controller;
- allows any unacknowledged missing final to pass;
- stops using the atomic snapshot-output handoff;
- enables network access during solve;
- removes immutable publication or prospective evaluation commands;
- removes a legacy compatibility workflow or restores any legacy automatic `schedule`/`push` trigger;
- points the scheduler at a SHA that does not contain the certified V2 production/evaluation contracts.

The contract also runs the operations regression suite from `ops_tests/` and the repository workflow-governance checker on every relevant PR.

The point is to make operational scheduling and recovery changeable without silently turning them into a second core-engineering surface.

## Updating the frozen pin

Do **not** update `FROZEN_APEX_SHA` merely because PR #90 advances, `main` advances, a dependency releases, or a challenger changes.

A pin change is allowed only after the replacement engine SHA satisfies the Apex freeze-break policy, including the required tests and production proof. The operations pin update should then be a small auditable PR containing only the scheduler pin/documentation change.

## Manual runs

Daily V2 production/evaluation and auth keepalive retain `workflow_dispatch` for incident recovery or an explicitly requested additional run. Manual execution is constrained to the default branch control plane, still checks out the frozen SHA and does not bypass privacy/publication contracts.

The three retired legacy workflows are also technically manual-only for compatibility. They are **not** part of normal operations and must never be used as an alternate canonical decision publisher.

Routine operation should rely on the V2 schedules. Additional pre-deadline V2 production runs should be used only when there is a material reason such as late injury/team news or an FPL rule/API/auth incident; do not create duplicate runs merely for reassurance. An auth keepalive is not a production rehearsal and cannot create a recommendation.

## Operational acceptance

The repaired daily layer is considered healthy when:

1. the operations repair PR is merged to the repository default branch (`main`);
2. the ops regression suite, governance, frozen-source and workflow-contract checks are green;
3. auth keepalive can rotate/persist a valid refresh state, or clearly reports that an external bootstrap re-seed is required;
4. evaluation runs through the six acknowledged historical failures while still proving there are no unacknowledged orphans;
5. the next justified production run uses the frozen SHA, authenticates the exact configured manager, freezes once, solves offline and creates its immutable matching final.

PR #90 remains draft and unmerged while this scheduler operates, because these workflows fetch the certified frozen SHA explicitly. Merging or changing PR #90 is not required to operate the frozen engine.
