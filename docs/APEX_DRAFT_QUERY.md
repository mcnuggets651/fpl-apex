# FPL Apex Draft Owner Query Runbook

This runbook defines the governed FPL Draft interaction/query path. It is **not** serving-model authority and cannot alter Classic FPL production decisions.

Machine serving authority remains [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json). Public continuity remains [`FPL_APEX_MASTER_STATE.md`](FPL_APEX_MASTER_STATE.md). Owner-private Draft results remain in `mcnuggets651/fpl`.

## Scope

The Draft capability supports fresh owner questions about:

- current Draft league and exact 15-player roster;
- available and locked players;
- public league transaction/trade history;
- authenticated entry-specific transaction state;
- current pending/open waiver requests **only after their exact upstream semantics are runtime-proven**;
- projection comparison by joining Draft identities to the authority-correct Apex projection query.

It does not perform waiver submissions, free-agent transactions, trades or other writes to Official FPL Draft.

## Identity

Configured owner surface:

- Draft league: `33160`;
- Draft entry name: `mcnuggets`.

The live team-entry ID must be resolved from Official Draft league details rather than treated as permanent configuration.

Draft element IDs and Classic FPL element IDs are separate namespaces. Cross-surface joins must reconcile **name + club + position**. Raw numeric ID equality is forbidden.

## Public/live Draft pool path

The private repository owns the live public Draft query:

- private request: `apex-query/draft_request.json`;
- private tool: `tools/apex_draft_query.py`;
- private workflow: `.github/workflows/apex-draft-query.yml`;
- private contract/runbook: `APEX_PRIVATE_QUERY_BRIDGE.md`;
- execution: `[self-hosted, macOS, ARM64]`, no hosted fallback.

Private PR #9 merged the first governed bridge. Post-merge workflow `33889278311` proved exact 15-player roster retrieval plus live available/locked pool retrieval. Entry-specific transactions reported `auth_required`, which isolated the authenticated transport requirement.

## Authenticated transaction path

Reusable FPL credentials remain owned by public `mcnuggets651/fpl-apex` through the existing certified owner-auth lifecycle. They are **not** copied into the private Draft workflow.

Public producer:

- workflow: `.github/workflows/apex-v2-draft-auth-relay.yml`;
- controller: `scripts/apex_v2_draft_auth_relay_ops.py`;
- authentication controller: current `main:scripts/apex_v2_auth_ops.py` using auth preflight/config/helpers resolved from machine authority `production_core_sha`;
- immutable `frozen_engine_sha`: ancestry/forensic proof only, never assumed to be the live auth implementation;
- concurrency: existing non-cancelling `apex-v2-fpl-auth` boundary;
- schedule: every 15 minutes plus manual and bounded push execution on `main`;
- authenticated transaction endpoint: Official Draft `draft/entry/<live_team_entry_id>/transactions`;
- authenticated schema diagnostic: Official Draft `entry/<live_team_entry_id>/my-team`.

The producer:

1. resolves `production_core_sha` and `frozen_engine_sha` from machine authority, proves the selected core descends from the immutable forensic base and materializes that core separately from `main`;
2. materializes the exact current control-plane relay/auth controllers and runs the auth controller against the authority-selected core preflight/config;
3. authenticates through the one serialized manager-identity/refresh/private-store boundary;
4. resolves the live Draft team-entry ID from public Official Draft league details;
5. fetches the authenticated entry transaction surface using the certified owner transport;
6. strips transaction output to at most 100 scalar allowlisted rows and adds safe player names from public Draft bootstrap data;
7. classifies transaction rows only as **resolved** (non-empty upstream `result`) or **unresolved** (missing/empty upstream `result`); unresolved is deliberately not renamed `pending` until runtime evidence proves that exact upstream semantic;
8. reads the authenticated `my-team` surface only for a **schema-only** diagnostic consisting of key names, container types, list counts and sample field names for transaction/waiver/request/pending/trade-like paths; it emits no owner scalar values from that surface;
9. recursively rejects credential-bearing keys;
10. sends the credential-free `apex-private-draft-auth-relay-v1` payload to private `mcnuggets651/fpl` via repository dispatch;
11. writes no owner transaction artifact to the public repository.

Private receiver:

- private tool: `tools/apex_draft_relay_ingest.py`;
- dispatch event: `apex-draft-auth-snapshot`;
- private workflow: `.github/workflows/apex-draft-query.yml`;
- private artifact: `apex-private-draft-auth-<private_workflow_run_id>`;
- stable private connected-session receipt: private issue `mcnuggets651/fpl#11`;
- artifact retention: seven days.

The private receiver validates exact league/entry/producer identity, successful authenticated status, approved auth mode, row count and field allowlist. It rejects keys containing token, cookie, authorization, secret or credential material. Private issue #11 contains only the revalidated allowlisted credential-free receipt and is never a Draft write surface.

## Resolved history is not an open waiver queue

The first stable authenticated receipt, produced on 4 September 2026, returned four event-3 waiver rows. Every row contained a non-empty upstream `result` code. Two successful incoming players were already present in the subsequent live roster. That is concrete evidence that the entry transaction endpoint includes **processed/resolved transaction history**.

Therefore:

- a row with a non-empty `result` must not be described as currently pending merely because it has a priority;
- result codes such as `a`, `di` and `do` must not be assigned guessed meanings without an upstream contract or independently verified runtime evidence;
- an empty transaction list alone is not yet sufficient proof of “no open waivers” unless the exact current-request surface being queried has been semantically established;
- a missing/empty `result` row is called `unresolved` until the relationship between that upstream state and the frontend's open waiver list is proven;
- if `my-team` or another authenticated GET exposes a distinct current waiver/request list, only that proven allowlisted surface may become the canonical pending/open queue.

This distinction is required because “authenticated transaction history works” and “current pending queue works” are different claims.

## Current owner-auth incident and permanent repair boundary

After PR #155 merged, authenticated Draft semantic discovery stopped before any Draft endpoint because owner authentication was unhealthy. Public PR #156 added only a failure-gated status probe and merged without changing recovery semantics. Its merged diagnostic established the exact current direct transport result: Official FPL `/api/me/` returned **HTTP 401 / `rejected`** for the configured static bearer. The rotating private refresh state and configured bootstrap refresh were also rejected. This is credential exhaustion/rejection evidence, not rate limiting or a 5xx incident.

The diagnosis also exposed a permanent crash/verification window in the prior refresh lifecycle: an identity-provider exchange could consume the parent refresh token before `/api/me/` manager verification, while the rotated child was not yet durable. A verification failure could therefore strand the refresh chain.

The governed repair is two-phase and remains inside existing `PROD-002` owner authentication:

1. recover any already-staged encrypted child for the current parent from authenticated private release listing before attempting a new exchange;
2. exchange the current refresh token once;
3. encrypt and upload the rotated child as a **private draft before** `/api/me/` verification;
4. treat that draft as inactive recovery evidence;
5. verify exact Classic manager identity;
6. only on exact match, re-download/digest-check and immutably publish the staged child as active refresh state;
7. on any indeterminate post-exchange verification result, retain the child staged and prohibit parent retry/bootstrap/direct fallback;
8. on explicit wrong-manager proof, strictly purge the wrong-manager staged chain or fail for manual private-store cleanup.

Production, Keepalive and Draft Relay must all use the same authority-selected production-core auth preflight/config and the same serialized `apex-v2-fpl-auth` concurrency group. The frozen PR #90 SHA remains forensic lineage and is never modified to fix authentication.

Because all currently configured durable credentials are rejected, one browser-issued refresh re-seed will still be required **after** this permanent repair is merged and exact-head accepted. The credential must be placed directly into the approved GitHub Actions secret and must never be pasted into chat, an issue, logs or documentation.

## Failure-only owner status diagnostic

The status-only probe retained after PR #156 is incident evidence, not authentication:

- it runs only after the owner-auth step has failed;
- it uses only already-configured static direct bearer/cookie transport;
- it performs one read-only streamed GET to Official FPL `/api/me/` per configured direct transport;
- it records only final HTTP status code and coarse class;
- it emits no response body, response headers, credential value, refresh token, private-repository token or manager payload;
- it does not parse manager identity and therefore cannot certify authentication;
- it does not retry, exchange, rotate or persist refresh state;
- it does not convert the failed owner-auth step into success and cannot unlock Draft query/dispatch.

The accepted diagnostic result for the current incident is 401/rejected. Do not keep probing or refreshing merely to reproduce that fact.

## Fresh-session ChatGPT rule

For a Draft owner question, a fresh connected agent must:

1. read public master state, machine authority, capability registry and this runbook;
2. use the approved private Draft query surface rather than chat memory or screenshots;
3. require a current successful public/live Draft result for roster and waiver-pool claims;
4. use the stable private `PRIV-009` receipt/private artifact for authenticated transaction evidence;
5. **never label resolved transaction-history rows as pending/open waivers**;
6. require the exact current-request semantic surface to be runtime-proven before asserting a pending/open queue or a confirmed empty queue;
7. use the authority-correct private Apex projection query for xP/model comparisons;
8. reconcile Draft↔Classic identities by name + club + position;
9. fail closed and state the exact missing surface if freshness, authentication, identity, transaction semantics or relay integrity cannot be verified.

A successful authenticated transaction-history response proves connectivity, not by itself the semantics of an open queue. `auth_required`, `auth_rejected`, endpoint failure, a stale receipt or ambiguous resolved/unresolved semantics must never be presented as “no open waivers.” A status-only owner-auth diagnostic is incident evidence only and must never be treated as an authenticated manager-state query.

## Project-instruction handoff

The ChatGPT Project instructions must not encode a provisional Draft pending-waiver query path. GitHub remains the durable source of truth while exact current-request semantics are incomplete.

After **all runtime-acceptance gates** below have passed, the connected ChatGPT session must explicitly tell the owner that the Draft connection is certified and provide the exact Project-instruction text to add. That final instruction must bind Draft owner questions to `PRIV-009`, require `OPS-008` for authenticated transaction evidence, preserve the live league/entry resolution and Draft↔Classic identity rules in this runbook, distinguish resolved history from current pending requests, forbid credential exposure or duplication, and fail closed when current authenticated evidence cannot be verified.

Until those runtime gates pass, the owner should leave existing Project instructions unchanged rather than paste provisional capability wording.

## Privacy and security invariants

- reusable FPL credentials never enter public artifacts, docs or logs;
- reusable FPL credentials are not duplicated into the private Draft query workflow;
- rotated refresh children are encrypted and staged only in the private auth release store;
- a staged child is never active until exact owner identity matches;
- consumed refresh parents are never blindly retried when a staged child exists;
- authenticated raw Draft response bodies are not logged or published;
- schema diagnostics contain no owner scalar values;
- owner-auth incident diagnostics contain only status code/class metadata and never read the response body;
- public control plane sends only the bounded credential-free relay contract;
- private owner transaction rows remain private;
- the stable private receipt is accessible only inside the private owner repository;
- the relay cannot solve, publish, change serving authority or submit Draft transactions;
- PR #90 remains `NEVER_MERGE_OR_ADVANCE`;
- AIrsenal serving authority is unchanged.

## Failure behavior

Fail closed when:

- manager authentication cannot be certified;
- a post-exchange refresh child cannot be durably staged, verified or activated;
- wrong-manager staged state cannot be purged;
- league/entry identity does not resolve uniquely;
- the authenticated transaction endpoint returns rejection/not-found/unexpected status;
- exact pending/open semantics are ambiguous;
- the payload exceeds the bounded dispatch size or row count;
- sensitive keys appear;
- private dispatch is rejected;
- private receiver validation fails;
- the current private artifact/receipt cannot be retrieved or verified.

Do not solve these failures by exposing credentials, copying raw authenticated responses, guessing result-code meanings, weakening validation, moving owner state public, submitting a test waiver without explicit governed write authorization, retrying a consumed refresh parent, falling back after an indeterminate staged rotation or falling back to chat memory.

## Runtime acceptance

CI proves structure. Historical connectivity already proved authenticated read/dispatch/private publication, but current authentication must be restored and **pending/open-waiver acceptance remains separate**.

Required closure order:

1. exact-head public Apex CI and Apex V2 Ops Contract pass for the two-phase auth/control-plane repair;
2. the exact repair head merges with machine authority and PR #90 unchanged;
3. a fresh browser-issued refresh credential is re-seeded directly into the approved GitHub Actions secret, never through chat;
4. merged Keepalive executes successfully and proves the two-phase rotation/private activation path;
5. merged `OPS-008` executes successfully, authenticates through the same path and dispatches a fresh credential-free private receipt;
6. schema-only diagnostics identify the exact authenticated current-request surface, or transaction rows are independently proven to represent unresolved current requests;
7. the producer extracts only the proven current-request surface through an explicit allowlist;
8. the private repository receives that state on merged receiver code and exposes a successful private artifact/stable receipt;
9. the private receipt is inspected and shown to represent the current pending/open queue, including a valid empty list only when the exact proven current-request surface itself is empty;
10. private public-capability binding validation passes against the final public runbook state.

Only after those gates are true may a fresh-session pending/open-waiver query be called permanently accepted.
