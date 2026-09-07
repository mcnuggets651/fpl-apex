# FPL Apex Draft Owner Query Runbook

This runbook defines the governed FPL Draft interaction/query path. It is **not** serving-model authority and cannot alter Classic FPL production decisions.

Machine serving authority remains [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json). Public continuity remains [`FPL_APEX_MASTER_STATE.md`](FPL_APEX_MASTER_STATE.md). Owner-private Draft results remain in `mcnuggets651/fpl`.

## Scope

The Draft capability supports fresh owner questions about:

- current Draft league and exact 15-player roster;
- available and locked players;
- legal waiver/free-agent swap construction from current roster/availability state;
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
- live decision guard: `tools/apex_draft_decision_guard.py`;
- stable live-state publisher: `tools/apex_draft_live_issue_publish.py`;
- private workflow: `.github/workflows/apex-draft-query.yml`;
- private contract: `DRAFT_LIVE_DECISION_CONTRACT.md`;
- stable connected-session roster/pool receipt: private issue `mcnuggets651/fpl#17`;
- execution: `[self-hosted, macOS, ARM64]`, no hosted fallback.

Private PR #9 merged the first governed bridge. Private PR #18, **Make live Draft recommendations fail closed**, merged at private SHA `7589aabfeb71b8043e437d90020764e5d1a35d28` on 7 September 2026 and converted the roster/pool query into a mechanically guarded interaction surface.

Merged private Draft run `34142054901` then passed end-to-end against the real Official Draft league: live query, decision guard, private artifact upload and issue #17 publication all succeeded. The accepted receipt was `READY`, target GW4, with exactly 15 owned players, 504 available rows, zero locked rows and `memory_fallback_allowed = false`. Those counts are runtime acceptance evidence only; a connected session must always fetch the **current** issue #17 rather than reuse these historical values.

### Live decision guard

Issue #17 may advance only after one same-run Official Draft query passes all of these checks:

- contract `apex-private-draft-live-decision-v1`;
- league ID exactly `33160` and entry name exactly `mcnuggets`;
- underlying query age no more than five minutes when guarded;
- exactly 15 unique owned players;
- roster composition exactly 2 GKP / 5 DEF / 5 MID / 3 FWD;
- current available and locked sets present;
- owned, available and locked Draft-element sets pairwise disjoint;
- current Draft position bound to every player row;
- exactly one current Official FPL `is_next` Gameweek;
- roster, available, locked and full-state SHA-256 bindings valid;
- `decision_preflight.recommendation_ready = true`;
- `memory_fallback_allowed = false`;
- `same_position_swap_required = true`;
- `incoming_must_be_available = true`;
- `outgoing_must_be_owned = true`;
- `owned_player_can_be_incoming = false`.

The guarded state expires 30 minutes after its live query timestamp; the workflow normally refreshes every 15 minutes. If query or guard publication fails, issue #17 is not advanced and the previous receipt expires naturally.

Every proposed waiver/free-agent swap must be validated against the exact same current issue #17 state: outgoing currently owned, incoming currently available, incoming not already owned or locked, and exact same current Official Draft position. The machine reference is `tools/apex_draft_decision_guard.py::validate_waiver_swap` in the private repository.

A football model, fixture edge or AI interpretation may rank only **already legal** swaps. It cannot override ownership, availability or positional legality.

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
- stable private connected-session authenticated receipt: private issue `mcnuggets651/fpl#11`;
- artifact retention: seven days.

The private receiver validates exact league/entry/producer identity, successful authenticated status, approved auth mode, row count and field allowlist. It rejects keys containing token, cookie, authorization, secret or credential material. Private issue #11 contains only the revalidated allowlisted credential-free receipt and is never a Draft write surface.

**Issue #17 and issue #11 are deliberately separate.** Issue #17 is mandatory current roster/available/locked state and legality evidence. Issue #11 is authenticated transaction/current-request evidence when that state matters. Neither may substitute for the other.

## Resolved history is not an open waiver queue

The first stable authenticated receipt, produced on 4 September 2026, returned four event-3 waiver rows. Every row contained a non-empty upstream `result` code. Two successful incoming players were already present in the subsequent live roster. That is concrete evidence that the entry transaction endpoint includes **processed/resolved transaction history**.

Therefore:

- a row with a non-empty `result` must not be described as currently pending merely because it has a priority;
- result codes such as `a`, `di` and `do` must not be assigned guessed meanings without an upstream contract or independently verified runtime evidence;
- an empty transaction list alone is not yet sufficient proof of “no open waivers” unless the exact current-request surface being queried has been semantically established;
- a missing/empty `result` row is called `unresolved` until the relationship between that upstream state and the frontend's open waiver list is proven;
- if `my-team` or another authenticated GET exposes a distinct current waiver/request list, only that proven allowlisted surface may become the canonical pending/open queue.

This distinction is required because “authenticated transaction history works” and “current pending queue works” are different claims.

## Owner-auth durability boundary

The 4–5 September credential incident established both a prior refresh-exhaustion condition and a crash/verification window in the old refresh lifecycle. Public PRs #157/#158 repaired refresh durability with staged-child persistence and exact activation; PR #169 subsequently added manager-certified cached-access reuse so frequent Draft relay polling does not rotate a one-time refresh parent on every successful authenticated invocation.

Current public master state is authoritative for live auth health. At the 6 September continuity snapshot, direct owner auth was operational through successful canonical production while durable refresh Keepalive remained degraded pending one fresh browser-issued refresh re-seed. Do not collapse those two health dimensions.

The governed two-phase refresh boundary remains:

1. recover any already-staged encrypted child for the current parent before attempting a new exchange;
2. exchange the current refresh token once;
3. encrypt and upload the rotated child as a private draft before manager verification;
4. treat that draft as inactive recovery evidence;
5. verify exact Classic manager identity;
6. only on exact match, re-download/digest-check and immutably publish the staged child as active refresh state;
7. on indeterminate post-exchange verification, retain the child staged and prohibit parent retry/bootstrap/direct fallback;
8. on explicit wrong-manager proof, strictly purge the wrong-manager staged chain or fail for manual private-store cleanup.

Production, Keepalive and Draft Relay all use the same authority-selected production-core auth preflight/config and serialized `apex-v2-fpl-auth` concurrency group. Frozen PR #90 remains forensic lineage and is never modified to repair authentication.

## Failure-only owner status diagnostic

The status-only diagnostic is incident evidence, not authentication:

- it uses only configured direct transports;
- it performs read-only Official FPL identity/status probing;
- it records only bounded status/mode metadata;
- it emits no response body, credential value, refresh token, private-repository token or manager payload;
- it cannot activate refresh state, solve, publish or unlock a failed Draft query.

A status-only diagnostic must never be treated as authenticated manager-state evidence.

## Fresh-session ChatGPT rule

For **every** Draft waiver/free-agent/drop/available-player/priority question, a fresh connected agent must:

1. read public master state, machine authority, capability registry and this runbook;
2. fetch private issue `mcnuggets651/fpl#17` before any model or football reasoning;
3. require the current #17 machine payload to pass the live-decision contract above, including `READY`, exact identity, expiry, exact roster composition, hashes and `memory_fallback_allowed = false`;
4. validate each proposed swap against that same #17 state: owned OUT, available IN, IN not owned/locked, same Official Draft position;
5. never use conversation memory, screenshots, old artifacts, previous squads or historical free-agent lists as a replacement for #17;
6. if #17 is absent, stale, malformed, identity-invalid, hash-invalid, expired or not `READY`, give **no waiver recommendation** and state the live-state blocker;
7. when authenticated current-request/pending transaction state matters, fetch private issue #11 separately and apply its independent freshness and semantic rules;
8. **never label resolved transaction-history rows as pending/open waivers**;
9. require the exact current-request semantic surface to be runtime-proven before asserting a pending/open queue or confirmed empty queue;
10. use the authority-correct private Apex projection query for xP/model comparisons only after state/legality gates pass;
11. reconcile Draft↔Classic identities by name + club + position.

A successful roster/pool receipt certifies current state/legality for its TTL; it does not certify pending/open transaction semantics. A successful authenticated transaction-history response proves connectivity, not by itself the semantics of an open queue.

## Project-instruction handoff

The **roster/available/locked and waiver-legality connection is now runtime-accepted** through `PRIV-009` issue #17. Project instructions may bind current Draft recommendation questions to this stable live-state receipt and require fail-closed behavior when it is not current/valid.

The **pending/open authenticated request queue remains a separate acceptance surface**. Project instructions must not claim that current pending/open waiver semantics are permanently certified until the independent issue #11/current-request runtime gates below are satisfied.

Any Project instruction must preserve:

- live league `33160` / entry `mcnuggets` resolution;
- issue #17 as mandatory current state/legality evidence;
- issue #11/`OPS-008` as separate authenticated transaction/current-request evidence;
- Draft↔Classic identity by name + club + position;
- no credential exposure or duplication;
- no Draft writes;
- fail closed rather than use memory.

## Privacy and security invariants

- reusable FPL credentials never enter public artifacts, docs or logs;
- reusable FPL credentials are not duplicated into the private Draft workflow;
- rotated refresh children are encrypted/staged only inside the governed private auth store;
- authenticated raw Draft response bodies are not logged or published;
- schema diagnostics contain no owner scalar values;
- owner-auth diagnostics contain only bounded status/mode metadata;
- public control plane sends only bounded credential-free relay state;
- private owner transaction rows remain private;
- stable private receipts are accessible only inside the private owner repository;
- issue #17 contains only allowlisted credential-free roster/available/locked decision state;
- issue #11 contains only validated credential-free authenticated receipt state;
- neither receipt can solve, publish, change serving authority or submit Draft transactions;
- PR #90 remains `NEVER_MERGE_OR_ADVANCE`;
- AIrsenal serving authority is unchanged.

## Failure behavior

Fail closed when:

- issue #17 cannot be fetched or fails identity/freshness/hash/roster/legality validation;
- an outgoing player is not currently owned;
- an incoming player is not currently available, is already owned or is locked;
- incoming/outgoing Draft positions differ;
- manager authentication cannot be certified when authenticated state is required;
- league/entry identity does not resolve uniquely;
- the authenticated transaction endpoint returns rejection/not-found/unexpected status;
- exact pending/open semantics are ambiguous;
- sensitive keys appear;
- private dispatch/receiver validation fails;
- current issue #11 evidence cannot be retrieved or verified when the question depends on it.

Do not solve these failures by exposing credentials, copying raw authenticated responses, guessing result-code meanings, weakening validation, moving owner state public, submitting a test waiver, or falling back to chat memory.

## Runtime acceptance

### Roster / available / locked / transaction-legality path — ACCEPTED

The current `PRIV-009` live-state interaction path is accepted for roster/pool facts and legal swap construction:

1. private PR #18 exact-head Draft regression workflow `34141826809` passed;
2. private exact-head master/public-capability binding workflow `34141826881` passed;
3. private exact-head strategy/runtime assurance workflow `34141827030` passed;
4. PR #18 merged unchanged at private main SHA `7589aabfeb71b8043e437d90020764e5d1a35d28`;
5. merged live Draft workflow `34142054901` completed **SUCCESS**;
6. its live query, fail-closed decision guard, artifact publication and stable issue publication all passed against the real configured Draft league;
7. private issue #17 published `READY` with exact 15-player roster and guarded current available/locked state;
8. the issue #17 contract mechanically rejects positional mismatches and already-owned incoming players and forbids memory fallback.

This acceptance is **freshness-bounded**, not perpetual data. A connected session must still fetch the current issue #17 and enforce `expires_at` every time.

### Pending/open authenticated request semantics — NOT YET PERMANENTLY ACCEPTED

Historical connectivity proves authenticated read/dispatch/private publication, but a current pending/open queue may be asserted only after all of these separate gates pass:

1. current owner authentication required for the surface succeeds through governed `OPS-008`;
2. schema-only diagnostics identify the exact authenticated current-request surface, or transaction rows are independently proven to represent unresolved current requests;
3. producer extracts only the proven current-request surface through an explicit allowlist;
4. private repository receives it on merged receiver code and exposes a current stable issue #11 receipt;
5. the receipt is inspected and shown to represent the current pending/open queue, including an empty list only when that exact proven surface itself is empty;
6. private public-capability binding validation passes against the final public runbook state.

Until those gates are true, do not call the pending/open-waiver query permanently accepted merely because roster/pool legality is accepted.
