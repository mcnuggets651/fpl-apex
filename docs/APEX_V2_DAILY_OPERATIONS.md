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

Owner authentication follows the same split. `main` owns the serialized operations transaction controller `scripts/apex_v2_auth_ops.py`; the preflight, auth-store primitives and configuration used by that controller are resolved from the authority-selected `production_core_sha`. The immutable `frozen_engine_sha` remains an ancestry/forensic anchor and is not the live auth implementation merely because it is frozen.

The only serving workflow is `.github/workflows/apex-v2-daily-production.yml`. **AIrsenal** is the sole serving provider H1–H8. Shadow/research paths have no serving authority.

## Active daily lifecycle

### Authentication keepalive

Workflow: `.github/workflows/apex-v2-auth-keepalive.yml`

Schedule: `22 */6 * * *` UTC.

The keepalive resolves the authority-selected production core, verifies its ancestry to the frozen forensic base, validates/rotates durable FPL owner credentials through the two-phase transaction described below, and verifies exact manager identity. It cannot acquire providers, solve or publish a recommendation. It shares the non-cancelling `apex-v2-fpl-auth` concurrency boundary with production and the Draft relay.

### Authenticated FPL Draft transaction relay

Workflow: `.github/workflows/apex-v2-draft-auth-relay.yml`

Runbook: [`APEX_DRAFT_QUERY.md`](APEX_DRAFT_QUERY.md).

Schedule: `7,22,37,52 * * * *` UTC plus manual dispatch and bounded `main` push execution for relay-contract changes.

The relay is an owner-query operation, not a serving path. It shares the same non-cancelling `apex-v2-fpl-auth` concurrency boundary as production/keepalive so refresh-state rotation cannot race. It:

1. resolves the same authority-selected production-core auth preflight/config used by production and proves that core descends from the immutable forensic base;
2. runs the current control-plane `scripts/apex_v2_auth_ops.py` transaction controller against those core-owned auth primitives;
3. proves the Classic owner credential before using the resulting certified bearer/cookie transport against Official FPL Draft;
4. resolves the live Draft team-entry ID from public league details for configured league `33160`, entry `mcnuggets`;
5. reads only the authenticated Draft entry transaction/current-state diagnostic surfaces allowed by `APEX_DRAFT_QUERY.md`;
6. strips the result to a bounded allowlist and refuses credential-bearing keys;
7. sends only the credential-free `apex-private-draft-auth-relay-v1` payload through repository dispatch to private `mcnuggets651/fpl`;
8. creates no public owner transaction artifact and performs no Draft write/waiver/trade action.

The private receiver lives on the repository-scoped self-hosted Mac and stores only the bounded private query evidence. If auth, identity, endpoint status, payload validation or dispatch fails, the relay fails closed and must not be interpreted as an empty pending-waiver queue.

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
6. validates/recovers authentication for entry 63984 using the main control-plane auth controller plus authority-selected core preflight/config;
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

The rotating owner credential is a serialized two-phase private transaction:

1. load the newest active encrypted private refresh state, or the explicitly configured bootstrap refresh only when bounded recovery permits it;
2. before exchanging a parent, recover any already-staged encrypted child for that exact parent from authenticated private release listing, so a consumed parent is never blindly retried;
3. exchange the current refresh token once;
4. immediately encrypt and durably upload the rotated child as a **private draft** before making `/api/me/` manager verification a success prerequisite;
5. verify the returned access token against the configured manager entry;
6. only after an exact manager match, re-download/digest-check the staged encrypted child and publish it immutably as active refresh state;
7. after successful activation, best-effort clean consumed intermediate staged drafts.

A staged draft is durable recovery evidence, **not active auth state**. Any network/unclassified/rejected access result after a successful exchange is `RefreshRotationIndeterminate`: leave the child staged, do not retry the consumed parent and do not fall through to bootstrap or direct authentication. The next serialized run must recover forward from that staged child. Explicit wrong-manager proof is different: the wrong-manager staged chain is strictly discarded; failure to purge it requires manual private-store cleanup and remains a hard failure.

The bounded recovery ladder is entered only when the refresh **exchange itself** is explicitly rejected/expired before a new child is staged. It may then try a configured bootstrap refresh token through the same two-phase transaction. For production only, direct bearer/cookie verification is allowed after both rotating and bootstrap refresh exchanges are explicitly rejected. Keepalive cannot substitute direct auth for a dead durable refresh chain.

If a browser-issued refresh credential is genuinely required because both durable refresh sources are expired, it must be re-seeded explicitly in GitHub Actions secrets; automation cannot manufacture a Premier League login. Never paste that credential into chat, logs, documentation or an issue.

The Draft relay deliberately reuses this one certified owner-auth lifecycle. It may not read/decrypt private refresh state independently, create a second refresh-token owner or bind itself permanently to the frozen forensic preflight.

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
- staged refresh rotation that cannot be durably created, recovered, verified or activated;
- any attempt to fall back after an indeterminate post-exchange refresh state;
- wrong-manager staged state that cannot be purged;
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

Generic `Apex CI` resolves the same authority-declared production core. The auth regression suite additionally verifies that production, keepalive and Draft relay all pass the authority-selected core preflight/config to the one current operations auth controller and remain inside the same non-cancelling auth concurrency group.

Operations or authority-reconciliation changes may touch only explicit allowlisted governance/workflow/documentation paths. Moving `production_core_sha` requires the separate deliberate successor certification/readiness/canary process; moving `frozen_engine_sha` is prohibited. Durable docs intentionally do not copy the movable serving SHA, so a future promotion can remain a one-file authority change.

## Runtime acceptance

CI is necessary but live state matters. An authentication repair is accepted only when the exact merged head receives a real secret/private-store runtime proof of the two-phase rotation after any required browser re-seed. A successor promotion requires exact-head assurance plus the read-only core readiness/canary proof before `production_core_sha` can change. For Decision Quality, see [`operations/PARALLEL_DECISION_LAB.md`](operations/PARALLEL_DECISION_LAB.md).

For authenticated Draft owner transactions, acceptance additionally requires a successful merged public relay run, a successful private repository-dispatch receiver run, inspection of the resulting credential-free private artifact and final private public-capability binding acceptance. Current open/pending waiver semantics remain separately fail-closed until `APEX_DRAFT_QUERY.md`'s exact current-request surface is runtime-proven.
