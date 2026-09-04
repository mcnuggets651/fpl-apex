# Apex V2 Daily Operations

Machine authority: [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json).

Immutable forensic base (`frozen_engine_sha`): `99cc7b51b0cff45462b567084cb1844cfe0a456f`

Current serving core: read `production_core_sha` from `APEX_V2_AUTHORITY.json`.

## Immutable forensic base / promoted production core / mutable control plane

PR #90 and its clean-room base are permanently anchored at:

`99cc7b51b0cff45462b567084cb1844cfe0a456f`

That value is `frozen_engine_sha`. It is a forensic/lineage anchor and **must never be advanced or repurposed as a promotion pointer**. PR #90 remains open/draft/unmerged with policy `NEVER_MERGE_OR_ADVANCE`.

The independently governed serving-code pointer is `production_core_sha` in `APEX_V2_AUTHORITY.json`. A production core must be a 40-character commit SHA descending from the immutable PR #90 base and must pass the full successor/readiness/canary gate before that pointer moves. The authority split and first hardened-core promotion are complete: the immutable base remains `99cc...`, while current serving code is always the separate authority-declared production core.

The default branch `main` is the mutable operations control plane. It owns bounded scheduling/orchestration/research controllers but does not become model authority. The canonical production workflow checks out `main`, resolves `production_core_sha`, proves ancestry to `frozen_engine_sha`, materializes the exact production core in a detached worktree and runs decision-driving code/config from that worktree.

The only serving workflow is `.github/workflows/apex-v2-daily-production.yml`. **AIrsenal** is the sole serving provider H1–H8. Shadow/research paths have no serving authority.

## Active daily lifecycle

### Authentication keepalive

Workflow: `.github/workflows/apex-v2-auth-keepalive.yml`

Schedule: `22 */6 * * *` UTC.

The keepalive validates/rotates durable FPL owner credentials, verifies exact manager identity and persists rotated private state. It cannot acquire providers, solve or publish a recommendation. It shares the non-cancelling `apex-v2-fpl-auth` concurrency boundary with production.

### Authenticated FPL Draft transaction relay

Workflow: `.github/workflows/apex-v2-draft-auth-relay.yml`

Runbook: [`APEX_DRAFT_QUERY.md`](APEX_DRAFT_QUERY.md).

Schedule: `7,22,37,52 * * * *` UTC plus manual dispatch and bounded `main` push execution for relay-contract changes.

The relay is an owner-query operation, not a serving path. It shares the same non-cancelling `apex-v2-fpl-auth` concurrency boundary as production/keepalive so refresh-state rotation cannot race. It:

1. uses the existing frozen owner-auth preflight plus current `scripts/apex_v2_auth_ops.py` controller;
2. proves the Classic owner credential before using the resulting certified bearer/cookie transport against Official FPL Draft;
3. resolves the live Draft team-entry ID from public league details for configured league `33160`, entry `mcnuggets`;
4. reads only the authenticated Draft entry transaction endpoint;
5. strips the result to a bounded allowlist and refuses credential-bearing keys;
6. sends only the credential-free `apex-private-draft-auth-relay-v1` payload through repository dispatch to private `mcnuggets651/fpl`;
7. creates no public owner transaction artifact and performs no Draft write/waiver/trade action.

The private receiver lives on the repository-scoped self-hosted Mac and stores only a seven-day private artifact. If auth, identity, endpoint status, payload validation or dispatch fails, the relay fails closed and must not be interpreted as an empty pending-waiver queue.

### Direct owner-auth diagnostic

Workflow: `.github/workflows/apex-v2-direct-auth-diagnostic.yml`

Trigger: **manual `workflow_dispatch` only**, and the job is restricted to `main`.

This is an incident-only diagnostic for the repository's directly supplied bearer/cookie credential. It deliberately disables refresh-token state and does not represent production authentication health. A rejected or expired direct token is a valid diagnostic failure; it must not cause every `main` push to go red while the managed refresh chain is healthy.

Do not add `push`, `schedule` or `workflow_run` triggers to this workflow. Do not use it as a keepalive fallback. `ops_tests/test_github_actions_runtime_contract.py` enforces the manual-only trigger and its non-serving boundary.

### Production

Workflow: `.github/workflows/apex-v2-daily-production.yml`

Schedule: `17 4 * * *` UTC.

Production:

1. checks out exact `main` as the control plane;
2. reads `production_core_sha` and the immutable `frozen_engine_sha` from the authority manifest;
3. proves the production core descends from the immutable base and materializes that exact core in a detached worktree;
4. installs the selected core, using its exact dependency lock when supported;
5. preflights the immutable private manager/release store;
6. validates/recovers authentication for entry 63984 using core-owned preflight/config;
7. creates immutable attempt intent tagged with the exact production-core SHA;
8. hashes Official FPL authority before provider work;
9. creates/acquires fresh governed provider surfaces, with AIrsenal serving H1–H8, using core-owned worker/config/upstream inputs;
10. re-anchors Official FPL and freezes inputs once, recording the same production-core SHA;
11. solves with `APEX_ALLOW_NETWORK_DURING_SOLVE=0` and core-owned architecture checks;
12. publishes private prerequisites and then the immutable final, again bound to the same production-core SHA.

The maximum production workflow runtime remains 120 minutes. Production is schedule/manual only; operations changes must not add an automatic push-triggered production rehearsal.

### Deadline watch

Workflow: `.github/workflows/apex-v2-deadline-watch.yml`

Schedule: `11,41 * * * *`.

It observes Official FPL and may dispatch the canonical production workflow roughly 90–150 minutes before a real deadline. It does not solve or publish itself.

### Daily evaluation

Workflow: `.github/workflows/apex-v2-daily-evaluation.yml`

Schedule: `41 6 * * *` UTC.

It audits immutable attempt/final state, prospectively scores newly completed Gameweeks from predeadline provider surfaces and rebuilds derived standings. The evaluation/tournament lineage may remain bound to the immutable frozen evaluator for comparable non-serving research. It cannot mutate the already sealed production decision or select the serving core.

## Authentication recovery

The normal production-core preflight loads the newest encrypted private refresh state, exchanges it, proves the configured manager and persists the rotated replacement before use.

A bounded recovery path is entered only for the classified rejected/expired refresh case. It may try a configured bootstrap refresh token through the same identity/persistence boundary and, for the production run only after both refresh paths are explicitly rejected, a directly verified owner credential. Wrong-manager identity, persistence failure, unexpected HTTP errors and all unclassified failures remain hard failures.

Keepalive cannot turn a direct credential into a durable pseudo-success. If a browser-issued refresh credential is genuinely required, it must be re-seeded explicitly; automation cannot manufacture a Premier League login.

The Draft relay deliberately reuses this certified owner-auth lifecycle. It may not read/decrypt private refresh state independently or create a second refresh-token owner.

## Immutable failed-attempt policy

Intent without final remains a production signal. Six previously investigated PR-era failed attempts are explicitly acknowledged in `scripts/apex_v2_attempt_audit_ops.py`; any other missing final is unacknowledged and daily evaluation fails closed.

The acknowledgement mechanism does not delete history, synthesize finals or hide new failures.

## Legacy publisher retirement

The old executable publishers are no longer present under `.github/workflows`:

- `pinnacle.yml`
- `airsenal.yml`
- `refresh-core-pin.yml`
- `gw1-final-2026.yml`

Their exact historical YAML is preserved under `archive/workflows/`, where it is inert. This removes obsolete direct-main/write-capable alternatives without deleting forensic history. Generic governance and the Apex V2 Ops Contract fail if those names return to the executable workflow directory.

Apex V2 serving AIrsenal acquisition is not the retired standalone `airsenal.yml`; it is part of the authority-declared production acquisition chain. The worker's upstream setup team ID `1` remains an intentional database-initialisation placeholder and is not production entry identity.

## Failure behavior

Fail closed on:

- malformed/missing authority pointers;
- any change to the immutable PR #90 forensic SHA;
- a production core that is not descended from the immutable base;
- private store/authentication/manager identity failure;
- Official FPL pre/post authority mismatch;
- invalid or incomplete snapshot handoff;
- serving-provider qualification failure;
- solve/mechanics/architecture failure;
- serving-core provenance disagreement;
- immutable publication failure;
- new unacknowledged missing final;
- Draft authenticated relay identity/auth/endpoint/payload/dispatch failure when pending-waiver state is requested.

Optional shadow failure is recorded under the production provider constitution and cannot become a serving fallback. Draft relay failure leaves serving authority unchanged and must not be converted into a guessed owner transaction state.

## Ops Contract

Workflow: `.github/workflows/apex-v2-ops-contract.yml`

It runs operations/research regressions against the exact frozen evaluator, separately verifies the authority-declared production core and its ancestry, rejects operations changes to engine `src/`/`config/`, verifies production/auth/evaluation/research safety boundaries, enforces Decision Quality runtime/no-hindsight contracts and verifies retired publishers remain archived/inert.

Generic `Apex CI` resolves the same authority-declared production core. When that core provides `requirements-v2.lock`, both the operations test job and readiness job install it under that exact lock and run its dependency-lock checker before exercising the core. This keeps operational readiness aligned with the sealed successor-certification environment while retaining the explicit compatibility fallback needed to rehearse older rollback cores without a lock.

Operations or authority-reconciliation changes may touch only explicit allowlisted governance/workflow/documentation paths. Moving `production_core_sha` requires the separate deliberate successor certification/readiness/canary process; moving `frozen_engine_sha` is prohibited. Durable docs intentionally do not copy the movable serving SHA, so a future promotion can remain a one-file authority change.

## Runtime acceptance

CI is necessary but live state matters. An operations repair is accepted only when the exact merged head receives the relevant live secret/private-store/runtime proof without changing serving semantics. A successor promotion requires exact-head assurance plus the read-only core readiness/canary proof before `production_core_sha` can change. For Decision Quality, see [`operations/PARALLEL_DECISION_LAB.md`](operations/PARALLEL_DECISION_LAB.md).

For authenticated Draft owner transactions, acceptance additionally requires a successful merged public relay run, a successful private repository-dispatch receiver run, inspection of the resulting credential-free private artifact and final private public-capability binding acceptance. See [`APEX_DRAFT_QUERY.md`](APEX_DRAFT_QUERY.md).
