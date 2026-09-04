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
- authentication controller: `scripts/apex_v2_auth_ops.py` plus the frozen preflight;
- concurrency: existing non-cancelling `apex-v2-fpl-auth` boundary;
- schedule: every 15 minutes plus manual and bounded push execution on `main`;
- authenticated transaction endpoint: Official Draft `draft/entry/<live_team_entry_id>/transactions`;
- authenticated schema diagnostic: Official Draft `entry/<live_team_entry_id>/my-team`.

The producer:

1. materializes the exact current control-plane relay/auth controllers while keeping the frozen auth worktree untouched;
2. authenticates through the existing manager-identity/refresh/private-store boundary;
3. resolves the live Draft team-entry ID from public Official Draft league details;
4. fetches the authenticated entry transaction surface using the certified owner transport;
5. strips transaction output to at most 100 scalar allowlisted rows and adds safe player names from public Draft bootstrap data;
6. classifies transaction rows only as **resolved** (non-empty upstream `result`) or **unresolved** (missing/empty upstream `result`); unresolved is deliberately not renamed `pending` until runtime evidence proves that exact upstream semantic;
7. reads the authenticated `my-team` surface only for a **schema-only** diagnostic consisting of key names, container types, list counts and sample field names for transaction/waiver/request/pending/trade-like paths; it emits no owner scalar values from that surface;
8. recursively rejects credential-bearing keys;
9. sends the credential-free `apex-private-draft-auth-relay-v1` payload to private `mcnuggets651/fpl` via repository dispatch;
10. writes no owner transaction artifact to the public repository.

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

## Owner-auth incident status diagnostic

The authenticated Draft relay depends on the same certified Official FPL owner-auth boundary as Classic production. If that certification fails with the frozen preflight's generic **unexpected status** error, the relay must remain failed and must not enter a new recovery path merely to keep Draft querying alive.

A bounded status-only diagnostic is permitted **after** that failed auth step:

- it uses only the already-configured static direct bearer/cookie transport;
- it performs one read-only GET to Official FPL `/api/me/` per configured direct transport;
- it uses streaming mode, records only the final HTTP status code and a coarse class (`ok`, `rejected`, `rate_limited`, `upstream_5xx`, `redirect`, `other_4xx`, `unexpected`, or `network_error`), and closes the response without reading its body;
- it emits no response body, response headers, credential value, refresh token, private-repository token or manager payload;
- it does not parse manager identity and therefore cannot certify authentication;
- it does not retry, exchange, rotate or persist refresh state;
- it does not convert the failed owner-auth step into success and cannot unlock the Draft query/dispatch step;
- frozen PR #90 and the frozen preflight remain untouched.

This diagnostic exists only to distinguish upstream rate limiting/service failure/endpoint behavior from credential rejection while preserving the existing fail-closed recovery constitution.

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
- league/entry identity does not resolve uniquely;
- the authenticated transaction endpoint returns rejection/not-found/unexpected status;
- exact pending/open semantics are ambiguous;
- the payload exceeds the bounded dispatch size or row count;
- sensitive keys appear;
- private dispatch is rejected;
- private receiver validation fails;
- the current private artifact/receipt cannot be retrieved or verified.

Do not solve these failures by exposing credentials, copying raw authenticated responses, guessing result-code meanings, weakening validation, moving owner state public, submitting a test waiver without explicit governed write authorization or falling back to chat memory. A diagnostic status code may explain a failure; it never authorizes bypassing it.

## Runtime acceptance

CI proves structure. Connectivity acceptance already proved authenticated read/dispatch/private publication, but **pending/open-waiver acceptance remains separate**.

For full pending/open acceptance:

1. exact-head public Apex CI and Apex V2 Ops Contract pass for the semantic-discovery/final extraction change;
2. the public producer executes from merged `main` and successfully authenticates;
3. schema-only diagnostics identify the exact authenticated current-request surface, or transaction rows are independently proven to represent unresolved current requests;
4. the producer extracts only the proven current-request surface through an explicit allowlist;
5. the private repository receives that state on merged receiver code and exposes a successful private artifact/stable receipt;
6. the private receipt is inspected and shown to represent the current pending/open queue, including a valid empty list only when the exact proven current-request surface itself is empty;
7. private public-capability binding validation passes against the final public registry/runbook state.

Only after those gates are true may a fresh-session pending/open-waiver query be called permanently accepted.
