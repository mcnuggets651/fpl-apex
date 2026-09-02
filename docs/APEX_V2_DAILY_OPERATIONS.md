# Apex V2 Daily Operations

Machine authority: [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json).

## Frozen engine / mutable control plane

Apex V2 core engineering is frozen at:

`99cc7b51b0cff45462b567084cb1844cfe0a456f`

Normal operations do not move that code pin. The default branch `main` owns bounded scheduling/orchestration/research controllers; production workflows check out and prove the frozen engine before execution. PR #90 remains open/draft/unmerged and is not an operations branch.

The only serving workflow is `.github/workflows/apex-v2-daily-production.yml`. **AIrsenal** is the sole serving provider H1–H8. Shadow/research paths have no serving authority.

## Active daily lifecycle

### Authentication keepalive

Workflow: `.github/workflows/apex-v2-auth-keepalive.yml`

Schedule: `22 */6 * * *` UTC.

The keepalive validates/rotates durable FPL owner credentials, verifies exact manager identity and persists rotated private state. It cannot acquire providers, solve or publish a recommendation. It shares the non-cancelling `apex-v2-fpl-auth` concurrency boundary with production.

### Direct owner-auth diagnostic

Workflow: `.github/workflows/apex-v2-direct-auth-diagnostic.yml`

Trigger: **manual `workflow_dispatch` only**, and the job is restricted to `main`.

This is an incident-only diagnostic for the repository's directly supplied bearer/cookie credential. It deliberately disables refresh-token state and does not represent production authentication health. A rejected or expired direct token is a valid diagnostic failure; it must not cause every `main` push to go red while the managed refresh chain is healthy.

Do not add `push`, `schedule` or `workflow_run` triggers to this workflow. Do not use it as a keepalive fallback. `ops_tests/test_github_actions_runtime_contract.py` enforces the manual-only trigger and its non-serving boundary.

### Production

Workflow: `.github/workflows/apex-v2-daily-production.yml`

Schedule: `17 4 * * *` UTC.

Production:

1. checks out/proves the frozen engine SHA;
2. preflights the immutable private manager/release store;
3. validates/recovers authentication for entry 63984;
4. creates immutable attempt intent;
5. hashes Official FPL authority before provider work;
6. creates/acquires fresh governed provider surfaces, with AIrsenal serving H1–H8;
7. re-anchors Official FPL and freezes inputs once;
8. solves with `APEX_ALLOW_NETWORK_DURING_SOLVE=0`;
9. runs the frozen architecture/mechanics checks;
10. publishes private prerequisites and then the immutable final.

The maximum production workflow runtime remains 120 minutes. Production is schedule/manual only; operations changes must not add an automatic push-triggered production rehearsal.

### Deadline watch

Workflow: `.github/workflows/apex-v2-deadline-watch.yml`

Schedule: `11,41 * * * *`.

It observes Official FPL and may dispatch the canonical production workflow roughly 90–150 minutes before a real deadline. It does not solve or publish itself.

### Daily evaluation

Workflow: `.github/workflows/apex-v2-daily-evaluation.yml`

Schedule: `41 6 * * *` UTC.

It audits immutable attempt/final state, prospectively scores newly completed Gameweeks from predeadline provider surfaces and rebuilds derived standings. It cannot mutate the already sealed production decision.

## Authentication recovery

The normal frozen preflight loads the newest encrypted private refresh state, exchanges it, proves the configured manager and persists the rotated replacement before use.

A bounded recovery path is entered only for the classified rejected/expired refresh case. It may try a configured bootstrap refresh token through the same identity/persistence boundary and, for the production run only after both refresh paths are explicitly rejected, a directly verified owner credential. Wrong-manager identity, persistence failure, unexpected HTTP errors and all unclassified failures remain hard failures.

Keepalive cannot turn a direct credential into a durable pseudo-success. If a browser-issued refresh credential is genuinely required, it must be re-seeded explicitly; automation cannot manufacture a Premier League login.

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

Apex V2 serving AIrsenal acquisition is not the retired standalone `airsenal.yml`; it is part of the frozen production acquisition chain. The worker's upstream setup team ID `1` remains an intentional database-initialisation placeholder and is not production entry identity.

## Failure behavior

Fail closed on:

- private store/authentication/manager identity failure;
- Official FPL pre/post authority mismatch;
- invalid or incomplete snapshot handoff;
- serving-provider qualification failure;
- solve/mechanics/architecture failure;
- immutable publication failure;
- new unacknowledged missing final.

Optional shadow failure is recorded under the frozen provider constitution and cannot become a serving fallback.

## Ops Contract

Workflow: `.github/workflows/apex-v2-ops-contract.yml`

It runs operations regressions against the exact frozen evaluator, rejects operations changes to frozen `src/`, `config/` or `tests/`, verifies production/auth/evaluation/research safety boundaries, enforces Decision Quality runtime/no-hindsight contracts and verifies retired publishers remain archived/inert.

Operations or authority-reconciliation changes may touch only explicit allowlisted governance/workflow/documentation paths. Engine pin replacement requires a separate deliberate certification and migration process.

## Runtime acceptance

CI is necessary but live state matters. An operations repair is accepted only when the exact merged head receives the relevant live secret/private-store/runtime proof without changing serving semantics. For Decision Quality, see [`operations/PARALLEL_DECISION_LAB.md`](operations/PARALLEL_DECISION_LAB.md).
