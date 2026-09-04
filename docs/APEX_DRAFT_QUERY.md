# FPL Apex Draft Owner Query Runbook

This runbook defines the governed FPL Draft interaction/query path. It is **not** serving-model authority and cannot alter Classic FPL production decisions.

Machine serving authority remains [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json). Public continuity remains [`FPL_APEX_MASTER_STATE.md`](FPL_APEX_MASTER_STATE.md). Owner-private Draft results remain in `mcnuggets651/fpl`.

## Scope

The Draft capability supports fresh owner questions about:

- current Draft league and exact 15-player roster;
- available and locked players;
- public league transaction/trade history;
- authenticated entry-specific pending/open transaction and waiver state;
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

Private PR #9 merged the first governed bridge. Post-merge workflow `33889278311` proved exact 15-player roster retrieval plus live available/locked pool retrieval. Entry-specific transactions reported `auth_required`, which isolated the remaining authenticated transport requirement.

## Authenticated pending-transaction path

Reusable FPL credentials remain owned by public `mcnuggets651/fpl-apex` through the existing certified owner-auth lifecycle. They are **not** copied into the private Draft workflow.

Public producer:

- workflow: `.github/workflows/apex-v2-draft-auth-relay.yml`;
- controller: `scripts/apex_v2_draft_auth_relay_ops.py`;
- authentication controller: `scripts/apex_v2_auth_ops.py` plus the frozen preflight;
- concurrency: existing non-cancelling `apex-v2-fpl-auth` boundary;
- schedule: every 15 minutes plus manual and bounded push execution on `main`;
- authenticated endpoint: Official Draft `draft/entry/<live_team_entry_id>/transactions`.

The producer:

1. materializes the exact current control-plane relay/auth controllers while keeping the frozen auth worktree untouched;
2. authenticates through the existing manager-identity/refresh/private-store boundary;
3. resolves the live Draft team-entry ID from public Official Draft league details;
4. fetches only the entry-specific transaction surface using the certified owner transport;
5. strips the result to at most 100 scalar allowlisted transaction rows and adds safe player names from public Draft bootstrap data;
6. recursively rejects credential-bearing keys;
7. sends the credential-free `apex-private-draft-auth-relay-v1` payload to private `mcnuggets651/fpl` via repository dispatch;
8. writes no owner transaction artifact to the public repository.

Private receiver:

- private tool: `tools/apex_draft_relay_ingest.py`;
- dispatch event: `apex-draft-auth-snapshot`;
- private workflow: `.github/workflows/apex-draft-query.yml`;
- private artifact: `apex-private-draft-auth-<private_workflow_run_id>`;
- retention: seven days.

The private receiver validates exact league/entry/producer identity, successful authenticated status, approved auth mode, row count and field allowlist. It rejects keys containing token, cookie, authorization, secret or credential material.

## Fresh-session ChatGPT rule

For a Draft owner question, a fresh connected agent must:

1. read public master state, machine authority, capability registry and this runbook;
2. use the approved private Draft query surface rather than chat memory or screenshots;
3. require a current successful public/live Draft result for roster and waiver-pool claims;
4. require a current successful authenticated private relay artifact for pending/open personal waiver claims;
5. use the authority-correct private Apex projection query for xP/model comparisons;
6. reconcile Draft↔Classic identities by name + club + position;
7. fail closed and state the exact missing surface if freshness, authentication, identity or relay integrity cannot be verified.

An empty authenticated transaction row list is valid only when the Official authenticated endpoint itself returned success and the private relay artifact records `status = ok`. `auth_required`, `auth_rejected`, endpoint failure or a missing relay artifact must never be presented as “no open waivers.”

## Project-instruction handoff

The ChatGPT Project instructions must not encode a provisional Draft query path. GitHub remains the durable source of truth while runtime acceptance is incomplete.

After **all five** runtime-acceptance gates below have passed, the connected ChatGPT session must explicitly tell the owner that the Draft connection is certified and provide the exact Project-instruction text to add. That final instruction must bind Draft owner questions to `PRIV-009`, require `OPS-008` for authenticated pending/open transaction state, preserve the live league/entry resolution and Draft↔Classic identity rules in this runbook, forbid credential exposure or duplication, and fail closed when current authenticated evidence cannot be verified.

Until those runtime gates pass, the owner should leave existing Project instructions unchanged rather than paste provisional capability wording.

## Privacy and security invariants

- reusable FPL credentials never enter public artifacts, docs or logs;
- reusable FPL credentials are not duplicated into the private Draft query workflow;
- authenticated raw Draft response bodies are not logged or published;
- public control plane sends only the bounded credential-free relay contract;
- private owner transaction rows are stored only as short-retention private workflow artifacts;
- the relay cannot solve, publish, change serving authority or submit Draft transactions;
- PR #90 remains `NEVER_MERGE_OR_ADVANCE`;
- AIrsenal serving authority is unchanged.

## Failure behavior

Fail closed when:

- manager authentication cannot be certified;
- league/entry identity does not resolve uniquely;
- the authenticated transaction endpoint returns rejection/not-found/unexpected status;
- the payload exceeds the bounded dispatch size or row count;
- sensitive keys appear;
- private dispatch is rejected;
- private receiver validation fails;
- the current private artifact cannot be retrieved or verified.

Do not solve these failures by exposing credentials, copying raw authenticated responses, weakening validation, moving owner state public or falling back to chat memory.

## Runtime acceptance

CI proves structure; full acceptance requires live evidence:

1. exact-head public Apex CI and Apex V2 Ops Contract pass;
2. the public producer executes from merged `main` and successfully authenticates/dispatches;
3. the private repository receives the dispatch on its merged receiver and produces a successful `apex-private-draft-auth-*` artifact;
4. the artifact is inspected and shown to represent the real authenticated entry transaction queue;
5. private public-capability binding validation passes after the public registry contains the Draft capability.

Only after all five are true may a fresh-session pending/open-waiver query be called permanently accepted.
