# Apex V2 Daily Operations

## Purpose

Apex V2 core engineering is frozen at:

`99cc7b51b0cff45462b567084cb1844cfe0a456f`

Daily operation must not move that code pin implicitly. The default branch owns only the scheduling/orchestration layer; every production and evaluation run explicitly checks out the certified frozen SHA before installing or executing Apex V2.

This separates two concerns:

1. **Frozen engine** — model/provider constitution, optimizer, FPL mechanics, acquisition/privacy contracts and publication code.
2. **Operations layer** — when the frozen engine runs and how failures/evaluations are surfaced.

Changing the schedule does not change the engine. Changing the engine requires a new certified SHA and a deliberate pin update after production proof.

## Active daily lifecycle

### 1. Production — 04:17 UTC every day

Workflow: `.github/workflows/apex-v2-daily-production.yml`

The job:

1. checks out the exact frozen Apex V2 SHA;
2. proves `HEAD` equals that SHA;
3. validates the separate immutable private manager store when authenticated mode is enabled;
4. validates/rotates the FPL owner credential before provider work;
5. creates the immutable attempt intent;
6. captures the Official FPL pre-provider authority hash;
7. generates a fresh AIrsenal H1-H8 candidate from the pinned AIrsenal upstream;
8. generates Dastan as an isolated best-effort shadow;
9. performs the V2 acquisition stage, including the other governed shadow/diagnostic providers, then re-anchors Official FPL and freezes the inputs once;
10. uses the explicit atomic `--snapshot-output` machine handoff introduced by the Production #40 permanent repair;
11. solves with `APEX_ALLOW_NETWORK_DURING_SOLVE=0` and the architecture check enabled;
12. publishes private prerequisites first and then the immutable public completed attempt;
13. uploads sanitized diagnostics only.

The production concurrency group is `apex-v2-production` with cancellation disabled. A slow run is therefore never silently replaced by a newer run.

Maximum workflow runtime remains 120 minutes, matching the certified production contract.

### 2. Evaluation — 06:41 UTC every day

Workflow: `.github/workflows/apex-v2-daily-evaluation.yml`

The evaluation is intentionally later than production. The normal gap is 2h24m; even a production run that reaches its 120-minute hard limit has a 24-minute separation before the scheduled evaluator begins.

The evaluator:

1. checks out and proves the same frozen SHA;
2. audits immutable intents/finals for orphaned production attempts;
3. preflights the private provider-evaluation store;
4. prospectively scores any newly completed Official FPL Gameweeks from the sealed pre-deadline provider surfaces;
5. rebuilds champion-challenger season standings;
6. uploads the derived standings artifact.

`evaluate-completed` is the lifecycle gate: if no new Official FPL Gameweek is complete, there is nothing to score. We do not fabricate outcomes or backfill forecasts after the deadline.

## Single canonical publisher

The following legacy workflows remain on the default branch only as **manual-only compatibility/forensic workflows**:

- `.github/workflows/pinnacle.yml` (`Apex Unified`)
- `.github/workflows/airsenal.yml` (standalone legacy AIrsenal worker)
- `.github/workflows/refresh-core-pin.yml` (legacy mutable Core-pin refresher)

Their old `schedule` triggers are removed, and `Apex Unified` also loses its automatic `push` trigger. Each keeps only `workflow_dispatch` so the existing legacy contract/governance tests can continue to validate those historical paths without letting them execute automatically. Their first line is an explicit `RETIRED: manual-only legacy workflow` marker.

This guarantees one automated operational decision publisher: **Apex V2 Daily Production**. AIrsenal remains the sole V2 serving provider H1-H8; challengers remain sealed/nonserving unless the formal promotion policy is satisfied.

## Why the old Core-pin refresher is retired

Apex V2 Proprietary does not trust a mutable pin written to the default branch. The certified proprietary worker resolves the current Core `main` revision during acquisition, rejects stale Core according to the frozen freshness policy, freezes the accepted revision into the run-local provenance chain and rejects source drift. Keeping the old six-hour repository pin writer would add mutation/noise without improving V2 truth. The legacy workflow remains manually invokable only for forensic/backward-compatibility purposes.

## Failure behavior

Daily automation is fail-closed.

- Authentication/private-store failure: production fails before provider work or publication.
- Official pre/post hash disagreement: acquisition fails; no decision is published.
- Missing/invalid snapshot handoff: production fails before solve.
- Solve failure after intent: final publication fails and the orphan is surfaced by `audit-attempts`.
- Serving-provider qualification failure: certification withholds action rather than silently blending/falling back.
- Optional shadow/diagnostic failure: recorded according to the frozen provider constitution; it cannot become serving output.
- Evaluation failure: does not modify the already sealed pre-deadline attempt; the next evaluation run may retry prospectively from immutable inputs.

## Schedule contract CI

Workflow: `.github/workflows/apex-v2-ops-contract.yml`

The operations PR is rejected if it:

- modifies `src/`, `config/`, `scripts/` or `tests/`;
- changes or removes the frozen SHA pin accidentally;
- removes the daily production/evaluation schedules;
- stops using the atomic snapshot-output handoff;
- enables network access during solve;
- removes immutable publication or prospective evaluation commands;
- removes a legacy compatibility workflow or restores any legacy automatic `schedule`/`push` trigger;
- points the scheduler at a SHA that does not contain the certified V2 production/evaluation contracts.

The point is to make operational scheduling changeable without silently turning it into a second core-engineering surface.

## Updating the frozen pin

Do **not** update `FROZEN_APEX_SHA` merely because PR #90 advances, `main` advances, a dependency releases, or a challenger changes.

A pin change is allowed only after the replacement engine SHA satisfies the Apex freeze-break policy, including the required tests and production proof. The operations pin update should then be a small auditable PR containing only the scheduler pin/documentation change.

## Manual runs

Both daily V2 workflows retain `workflow_dispatch` for incident recovery or an explicitly requested additional run. Manual execution must still use the frozen SHA and the same privacy/publication contracts. It is not a bypass around certification.

The three retired legacy workflows are also technically manual-only for compatibility. They are **not** part of normal operations and must never be used as an alternate canonical decision publisher.

Routine operation should rely on the V2 daily schedules. Additional pre-deadline V2 runs should be used only when there is a material reason such as late injury/team news or an FPL rule/API incident; do not create duplicate runs merely for reassurance.

## Operational acceptance

The daily layer is considered live only when:

1. the operations PR is merged to the repository default branch (`main`), because GitHub scheduled workflows run from the default branch;
2. the first scheduled production run completes successfully at the frozen SHA;
3. its immutable intent/final releases and sanitized diagnostics are present;
4. the following evaluation run completes and produces/updates the prospective tournament artifact without an orphaned-attempt error.

PR #90 may remain draft and unmerged while this scheduler operates, because these workflows fetch the certified frozen SHA explicitly. Merging or changing PR #90 is not required to operate the frozen engine.
