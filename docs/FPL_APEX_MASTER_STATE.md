# FPL Apex — Canonical Master State

> **MANDATORY CONTINUITY FILE — READ BEFORE ANY SUBSTANTIVE WORK**
>
> This is the canonical **human/project continuity ledger** for FPL Apex. It exists so a fresh ChatGPT, Codex, Claude, human maintainer, or CI operator can recover the project without relying on conversation memory.
>
> It does **not** replace machine authority or immutable evidence. Where this prose conflicts with machine-verifiable state, the precedence rules below apply and this file must be corrected in the same change that discovers the conflict.

**Ledger schema:** 1  
**State snapshot:** 4 September 2026, after PR #155 open-waiver semantic hardening merged and during bounded Official FPL owner-auth upstream-status diagnosis  
**Season:** 2026/27  
**Public control-plane repository:** `mcnuggets651/fpl-apex`  
**Private persistence/query repository:** `mcnuggets651/fpl`  
**Production Classic entry:** `63984`

---

## 0. Authority and precedence — never improvise this

When sources disagree, use this order:

1. **Immutable release evidence and current GitHub facts** — immutable release payloads/attestations/digests, current branch/PR/workflow state and live Official FPL facts.
2. **Machine production authority** — `docs/APEX_V2_AUTHORITY.json`.
3. **This master state ledger** — the canonical human continuity/history/next-step record.
4. **Capability registry** — `docs/APEX_CAPABILITY_REGISTRY.yaml`, the semantic index of capabilities/change surfaces; it is not serving authority.
5. **Current system map and supporting Project Brain documents** — `docs/APEX_ARCHITECTURE.md`, `CURRENT_STATE.md`, `APEX_MASTER_CONTEXT.md`, `APEX_OPERATING_MANUAL.md`, `APEX_DECISIONS.md` and operational runbooks.
6. **Conversation/project memory** — useful context only; never authority for squad, prices, transfers, SHAs, release identity, model state, Draft roster/waivers or production readiness.

If a fresh session cannot reconcile tiers 1–3, it must stop before making a manager recommendation or changing production and resolve the discrepancy from GitHub/release evidence.

### Mandatory startup read order

Before changing code, workflows, governance, model behavior, production operations, query behavior, documentation that asserts current state, or manager-facing decision logic:

1. read this file completely;
2. read `docs/APEX_V2_AUTHORITY.json`;
3. read `docs/CURRENT_STATE.md` and `docs/APEX_OPERATING_MANUAL.md`;
4. read `docs/APEX_CAPABILITY_REGISTRY.yaml` and `docs/APEX_ARCHITECTURE.md`;
5. read the specific runbook/contract/tests referenced by the registry for the capability being touched;
6. verify live GitHub `main`, relevant PRs, required checks/ruleset and immutable release/workflow state;
7. for owner-specific questions, use the private query boundary — never reconstruct manager or Draft state from chat memory.

`AGENTS.md` and `CLAUDE.md` encode this startup contract for automated agents. CI enforces both same-change master continuity and semantic capability/change-surface coverage.

---

## 1. Current executive status

# **APEX OPERATIONAL**

The serving production chain and accepted Classic owner-private query chain have completed their required acceptance. The live FPL Draft roster/market connection and the authenticated transaction relay are also runtime-proven. One narrower Draft claim remains deliberately uncertified: the exact **current open/pending waiver-request semantics**. The first authenticated stable receipt proved that the known entry transaction endpoint includes processed history, so resolved history must not be mislabeled as the current open queue.

A new live incident on 4 September 2026 is currently blocking further authenticated Draft semantic discovery: Official FPL `/api/me/` began returning the frozen preflight's generic **unexpected status** from GitHub-hosted runners. This has now reproduced both after refresh-token exchange and through the independent static direct-bearer diagnostic. The system is correctly failing closed. Do not call this a credential rejection, rate limit or outage until the bounded status-only diagnostic identifies the exact HTTP class.

Canonical production run `33850307770-1` proved AIrsenal serving and the owner decision path. A later bounded Dastan H1 shadow orchestration repair merged through public PR #153; Dastan and PITCHSIDE remain research-only and none of the Draft work changes serving authority.

### Production acceptance

Canonical production run #9 completed successfully and produced a matched immutable public/private release pair for 2026/27 GW3.

- workflow run: `33850307770`;
- immutable run ID: `33850307770-1`;
- production core: `c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437`;
- frozen forensic base: `99cc7b51b0cff45462b567084cb1844cfe0a456f`;
- serving provider: AIrsenal H1–H8;
- authentication: passed;
- Official FPL acquisition: passed;
- AIrsenal generation: passed;
- frozen solve: passed;
- publication witness: passed;
- public final release write: passed;
- private manager release write: passed;
- observed production runtime: approximately four minutes.

### Owner-private Classic query acceptance

The former GitHub-hosted billing blocker has been eliminated without increasing spending limits. Private repo `mcnuggets651/fpl` uses a dedicated repository-level self-hosted runner on the existing Mac:

- runner: `fpl-apex-private-mac`;
- labels: `self-hosted`, `macOS`, `ARM64`;
- machine: `BC02336`;
- observed runner version: `2.337.0`;
- no `ubuntu-latest` fallback.

Required strategy acceptance modes both executed successfully:

- explicit exact run `33850307770-1`: strategy workflow `33868412431` — **success**;
- restored authority-selected `latest`: strategy workflow `33868662109` — **success**;
- final private master-state contract `33868662187` — **success**.

Exact and final `latest` narrow strategy JSON were byte-for-byte identical at SHA-256:

`e50c4ebde19a2c68bfa4c38f33a6dd81f1d0922851f1e932bae522a898609d60`

Both resolved immutable run `33850307770-1`, entry `63984`, exactly 15 unique owned players, bank £0.5m, 1 free transfer, no active chip, complete purchase/selling prices, complete transfer state and narrow private-safe output only.

### Current provider-query closure

Private PR #8 repaired the chat-facing projection request that was still explicitly pinned to historical run `33719526625-1` after the accepted strategy path had moved to authority-selected `latest`.

- PR #8 exact head: `95d62c985acb838c5df9b830ad0051036c114783`;
- exact-head private master-state contract `33880335918`: success;
- merge commit: `2f4ac141224f1fe222de6893a544abfbf685ea6a`;
- post-merge private master-state contract `33880420453`: success;
- post-merge projection query `33880420585`: success;
- projection artifact ID `9939639578`, digest `sha256:c611bff6edbf49d8fbeeb92ea84e75c58d3404d37c86c6f84fc06393de847754`.

That query resolved exact current immutable run `33850307770-1`, the matching private evaluation namespace and the matching private PITCHSIDE tournament namespace. It exposed current PITCHSIDE rows for the requested strategy universe. The same-run provider archive contained AIrsenal only because Dastan had failed earlier during production acquisition; the private query bridge itself was no longer the Dastan blocker.

### FPL Draft owner-query closure — connection/relay accepted; exact open-waiver semantics under bounded discovery

The live Draft connection itself is proven and does not depend on chat memory.

Private PR #9, **Add private live FPL Draft query bridge**, merged at:

`6474254554b3b5f2500fdad2005ee90fb7c0656f`

Post-merge private Draft workflow `33889278311` succeeded on the self-hosted Mac and proved the current Official Draft surface for league `33160`, entry `mcnuggets`:

- exact roster count: 15;
- roster complete: true;
- available players: 478;
- locked players: 24;
- public league transaction history: readable;
- public league trades: readable;
- entry-specific transaction endpoint: `auth_required`.

That result proved the league/account/roster/waiver-pool connection is healthy and isolated the remaining defect at that point to authenticated transport. It also proved reusable FPL authentication is not present in the private Draft workflow environment and therefore must not be guessed or silently treated as an empty queue.

Private PR #10 then added the credential-free authenticated-relay receiver:

- exact head: `8dcef5e3c961e5fe3408a523526db1b0ec3f942f`;
- exact-head `Apex Private Draft Query` run `33892177717`: success;
- exact-head `Apex Private Master State Contract` run `33892177813`: success;
- merge commit: `e215785fdfecd37cee967ffec9a66cf45e6e9d85`.

Public PR #154, **Complete governed FPL Draft authenticated owner-query relay**, then closed the authenticated transport and semantic registration:

- exact head: `10728ba721e325639a71e4e998960c9c32a49fde`;
- exact-head Apex CI `33896311945`: success;
- exact-head Apex V2 Ops Contract `33896311949`: success;
- merge commit/authenticated-relay public baseline: `4a37729b7cf38a72a48a511fbeb60c7decb89af4`;
- `OPS-008` authenticated Draft transaction relay registered;
- `PRIV-009` live Draft owner query registered;
- `INT-001` depends on `PRIV-009`.

The merged public relay successfully authenticated and queried the real entry transaction endpoint. Public run `33896772261` passed certified owner credential acquisition, authenticated Draft transaction acquisition, private dispatch and frozen-worktree proof.

Private PR #12, **Certify stable private FPL Draft owner query surface**, then closed the connected-session read target:

- exact head: `6c7eedb301958dff79d26be9363db3f96b76b7dc`;
- exact-head private Draft run `33897979229`: success;
- exact-head private master/public-capability contract `33897979355`: success;
- merge commit/current private baseline: `e089b31be4bea257a27964fd52951822d68dc324`;
- stable private machine-managed receipt: private `mcnuggets651/fpl` issue #11;
- private event-class concurrency was separated so PR certification, scheduled pool queries and authenticated relay ingestion wait rather than cancel each other.

A fresh post-merge public relay rerun `33897685281` successfully dispatched into current private `main`. Private repository-dispatch run `33898312773` then passed:

- relay validation;
- private artifact upload;
- stable private issue #11 publication.

Private artifact:

- `apex-private-draft-auth-33898312773`;
- artifact ID `9946749382`;
- digest `sha256:4d2b41366c350eb96042cdd6037d660c5d0828139cd4d8722416eaaca6a503b1`.

The stable receipt proved authenticated connectivity for live Draft team-entry ID `172178` and returned four event-3 waiver rows. Every returned row had a non-empty upstream `result` code. Two successful incoming players were already present in the subsequently observed roster. This proves that `draft/entry/<team_entry_id>/transactions` includes **processed/resolved transaction history**.

Therefore the four rows in the first receipt are not evidence of the current open queue. Result-bearing history must not be described as pending. Upstream result codes such as `a`, `di` and `do` must not be assigned guessed meanings without verified semantics.

Public PR #155, **Harden FPL Draft open-waiver semantics**, then merged the bounded read-only semantic-discovery contract:

- exact head: `9315fa90ba1c23bfaf8c4a51c281aea73fa6e1f2`;
- exact-head Apex V2 Ops Contract `33899930818`: success;
- exact-head Apex CI `33899930858`: success;
- merge/current public `main` before the status-diagnostic change: `a533a9bcd25699f0f9fe444f11487ac271923471`;
- transaction rows are classified as `resolved` when upstream `result` is non-empty and `unresolved` when it is absent/empty;
- `unresolved` is deliberately not renamed `pending` until runtime evidence proves that exact relationship;
- authenticated `entry/<live_team_entry_id>/my-team` is queried only for a schema-only diagnostic;
- the diagnostic may expose key names, container types, list counts and sample field names for transaction/waiver/request/pending/trade-like paths, but never owner scalar values;
- no Draft POST/DELETE/write path was introduced.

Immediately after PR #155 merged, push-triggered relay `33901095469` failed **before any Draft endpoint was queried** at `Acquire certified owner credential`. The frozen preflight reported `Official FPL owner-auth preflight returned an unexpected status`, which means the observed `/api/me/` status was not `200`, `401` or `403` but did not expose the exact code. One bounded failed-job rerun of the same SHA reproduced the same failure. Blind retries were stopped.

To separate refresh-token behavior from the Official FPL owner endpoint itself, the existing non-serving `OPS-002` direct-auth diagnostic was rerun from historical workflow run `33662138778` using current repository secrets. It disabled refresh authentication entirely and again failed at frozen `/api/me/` verification with the **same unexpected-status class**. Therefore the current incident is not established as a normal credential rejection and is not isolated to refresh-token rotation. The exact upstream status still requires bounded diagnosis.

Current bounded branch `agent/auth-owner-me-status-diagnostic` adds only a post-failure status probe to `OPS-008`:

- it runs only after the certified owner-auth step fails;
- it uses the already-configured static direct bearer/cookie only;
- it performs one streamed GET to Official FPL `/api/me/` per configured direct transport;
- it records only final HTTP status code plus coarse class and closes the response without reading the body;
- it reads no response body or response headers and emits no credential values;
- it does not exchange, rotate, retry or persist refresh state;
- it does not recover authentication, does not unlock Draft querying/dispatch and leaves the job failed;
- frozen PR #90 and the frozen preflight remain untouched.

**Do not call current pending/open waiver retrieval certified yet.** The connection, historical authenticated relay, private artifact and fresh-session stable receipt are accepted. Current authenticated semantic discovery is temporarily blocked by the new owner-auth upstream-status incident. First identify the exact status class without weakening fail-closed auth; then restore/verify certified owner authentication before resuming schema-only open-waiver discovery.

### Operational qualification

`APEX OPERATIONAL` means a fresh connected agent can reproducibly recover and verify the authority-correct immutable Classic owner state without relying on remembered squad information. It can also recover current Draft roster/available/locked state and the last accepted authenticated private transaction-history evidence through the governed Draft query/relay path.

It does **not** mean stale authenticated Draft evidence may substitute for a current successful auth run, nor does it mean a fresh session may assert personal pending/open Draft waiver requests solely from result-bearing historical transaction rows. Current owner-auth status, production freshness, deadline, Official FPL, exact Draft transaction semantics and provider-qualification gates continue to determine whether a new manager-facing recommendation is actionable.

---

## 2. Current live repository/authority snapshot

These values are a dated continuity snapshot. At session start verify live GitHub; never treat a mutable `main` SHA as permanent.

### Public repository

- repository: `mcnuggets651/fpl-apex`;
- public continuity PR #150 merged successfully on 4 September 2026 at `a00f0a45d8e74d834f79cbc473a6482656b9feda`;
- PR #150 exact-head Apex CI `33870084591`: success;
- PR #150 exact-head Apex V2 Ops Contract `33870084665`: success;
- post-merge Apex CI `33870475132`: success;
- capability/documentation constitution PR #151 merged at `6a1509f766e6438a43d296e8e900518a18967959` after exact-head Apex CI `33873835393` and Ops Contract `33873835399`; post-merge Apex CI `33874537255`: success;
- PR #152 closed the final documentation-only loop and merged at `620ad5d305008c018c9ea3ccd887c9de8b510b9c` after exact-head Apex CI `33877989903` and Apex V2 Ops Contract `33877990068` passed;
- PR #153, **repair Dastan shadow acquisition core-root wiring**, merged at `adf7c22058ef9b384793fabdad6853259d23a648`;
- PR #154, **Complete governed FPL Draft authenticated owner-query relay**, merged at authenticated-relay public baseline `4a37729b7cf38a72a48a511fbeb60c7decb89af4` after exact-head Apex CI `33896311945` and Ops Contract `33896311949` passed;
- PR #155, **Harden FPL Draft open-waiver semantics**, merged at current public baseline `a533a9bcd25699f0f9fe444f11487ac271923471` after exact-head Apex CI `33899930858` and Ops Contract `33899930818` passed;
- bounded owner-auth diagnostic branch: `agent/auth-owner-me-status-diagnostic`;
- protected control plane; historical ruleset identifier `21759706` — verify live before relying on it.

### Machine authority

`docs/APEX_V2_AUTHORITY.json` was re-read before the owner-auth diagnostic change and remains unchanged:

- `schema_version`: `1`;
- `season`: `2026-2027`;
- `entry_id`: `63984`;
- `frozen_engine_pr`: `90`;
- `frozen_engine_sha`: `99cc7b51b0cff45462b567084cb1844cfe0a456f`;
- `frozen_engine_pr_policy`: `NEVER_MERGE_OR_ADVANCE`;
- `production_core_sha`: `c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437`;
- canonical production workflow: `.github/workflows/apex-v2-daily-production.yml`;
- serving provider: `airsenal`;
- serving horizons: 1–8;
- AIrsenal role: `CHAMPION`, serving authorized;
- Dastan role: `SHADOW`, H1 only, serving unauthorized;
- PITCHSIDE role: `SHADOW`, H1–H8, serving unauthorized;
- research production influence: `NONE`;
- automatic promotion: `false`;
- legacy status: `HISTORICAL_NON_SERVING`.

The Draft owner-query/relay/semantic-discovery/status-diagnostic work does not change machine authority.

### Frozen PR #90

PR #90, **Build Apex V2 clean-room production architecture**, remains deliberately open, draft, unmerged, not an operations branch and not a branch to advance as part of successor promotion.

The immutable authority anchor is forensic SHA `99cc7b51b0cff45462b567084cb1844cfe0a456f`. The policy remains **NEVER_MERGE_OR_ADVANCE**.

### Private repository

- repository: `mcnuggets651/fpl`;
- accepted final-latest merge commit: `a310450fd27aa469eac9ae91971334925b4bee77`;
- private capability/documentation binding PR #7 merged at `459427fe1e90565d61f8a9f6547f3876c4f3ec9a`;
- current-provider query PR #8 merged at `2f4ac141224f1fe222de6893a544abfbf685ea6a`;
- live Draft query PR #9 merged at `6474254554b3b5f2500fdad2005ee90fb7c0656f`; post-merge Draft query `33889278311`: success;
- authenticated Draft relay receiver PR #10 merged at `e215785fdfecd37cee967ffec9a66cf45e6e9d85` after exact-head Draft query `33892177717` and private master contract `33892177813` succeeded;
- stable connected-session Draft surface PR #12 merged at current private baseline `e089b31be4bea257a27964fd52951822d68dc324` after exact-head Draft run `33897979229` and private master/public-capability contract `33897979355` succeeded;
- current-main repository-dispatch `33898312773` successfully validated the authenticated relay, uploaded artifact `9946749382` and published stable private issue #11;
- private CI consumes and validates the single public capability registry and rejects a competing private registry;
- owner-private payloads, exact manager commitments, Draft owner transactions and authentication material remain private.

---

## 3. Successful immutable GW3 production proof

### Public final

Tag: `apex-v2/final/2026-2027/33850307770-1`

- release ID: `382559137`;
- immutable: yes;
- published: `2026-09-04T07:51:49Z`;
- target commitish: `c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437`.

Assets and GitHub release digests:

| Asset | SHA-256 |
|---|---|
| `attestation.json` | `0060809dc7701f13e15972ae0678b47e033632a5faf43bae0560002e535f24cd` |
| `canonical_forecast.json` | `571deb99380d93de14f577a1f8369cf79afab83ae810159072aae218b8ababef` |
| `evidence.json` | `aba8d632da8130d41f13fe230f8af4e34255c4af713974654b3cf44b4ffa7fbd` |
| `governance.json` | `1d645c59bca4dc67fbfd466e939793d7086500b4a0d710a02c6d4233ba08f979` |
| `provider_forecasts.tar.gz` | `62e6acac24f1b3c772524d7b6cc4b9b38dd60b12d37d08a19ab6399383d9ee71` |
| `public_attempt.json` | `3c5ec47f5f02e42ee192bd57634a573468891965165582550799d67889d1bd2b` |

### Matching private finals

The private persistence repository contains matching immutable run identity `33850307770-1` in:

- `apex-v2/private/2026-2027/33850307770-1`;
- `apex-v2/private-evaluation/2026-2027/33850307770-1`;
- `apex-v2/private-presentation/2026-2027/33850307770-1`;
- `apex-v2/private-tournament/2026-2027/33850307770-1`.

Exact private payload/digest details belong in the private master companion, not in this public repository.

### Architectural conclusion proved by run #9

The two-repository design is valid:

- `fpl-apex` is the public control plane, machine authority and research-safe publication plane;
- `fpl` is the owner-private persistence/query plane;
- the earlier long-run failure was duplicate time-bounded optimisation/publication behavior, **not** the repository split.

Do not collapse the repositories or move private manager/Draft state into the public repo to simplify querying.

### Dastan incident and bounded repair

The sanitized diagnostic artifact `apex-v2-diagnostic-33850307770-1` proved the optional Dastan step failed in the successful serving run with control-plane/core working-directory `KeyError: 'dastan'` evidence while `serve_authorized = false` and `production_influence = NONE`.

Public PR #153 subsequently merged the bounded orchestration repair so Dastan helper execution resolves repo-relative locks/config/scripts from the authority-selected production-core root. This repair did not alter machine authority, AIrsenal serving status, PR #90 or Draft behavior. Live runtime evidence, not the merge alone, decides current Dastan health.

---

## 4. Production defect that was permanently closed

### Defect A — duplicate optimisation during publication

The old production path performed the expensive H1–H8 candidate MIP search in the primary solve and reran it during publication. Repeated approximately 120-second MIPs expanded runtime to roughly 68 minutes and allowed time-bound solver-search details to differ, causing false nondeterminism.

### Defect B — incorrect one-candidate semantics

Even with one candidate requested, the optimiser ran primary, secondary and excluded-path MIPs and returned the secondary result while describing the primary as retained. Multi-week transfer decisions were also recorded with `horizon=1`, causing valid multi-week transfer paths to fail certification.

### Permanent repair — PR #146

PR #146, **Make production single-solve and publication witness-only**, implemented the bounded permanent fix and was merged into the promoted production core.

Production now explicitly uses `candidate_limit=1`, executes exactly one primary MIP in the one-candidate path, retains the actual primary max-xP solution, records the true qualified planning horizon, never reruns the optimiser during publication and uses a deterministic frozen publication witness.

Verification included 42 relevant local tests, one-candidate invocation proof, semantic mutation sentinels, lint, exact-head Apex CI `33846244269` and exact-head Apex V2 CI `33846244193`.

### Authority promotion — PR #147

PR #147 promoted repaired exact core `c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437` after Apex V2 Ops Contract `33847263015` and Apex CI/readiness `33847263087` succeeded.

This is closed production engineering. **Do not reopen it without new reproducible defect evidence.**

---

## 5. Authentication recovery — historical closure plus current upstream-status incident

Before production run #8, stored FPL tokens expired. Auth keepalive #22 failed and both rotating private refresh state and bootstrap refresh secret were rejected.

A fresh authenticated FPL browser session renewed the encrypted Actions secret. The credential was immediately exchanged/rotated and persisted through the private rotating state.

Acceptance run:

- auth keepalive `33850189866`: success;
- private-store preflight: passed;
- credential rotation: passed;
- new rotating state: persisted;
- frozen worktree integrity: passed.

The temporary browser refresh credential was rotated before production and is not the active credential. Never write credentials, token values or authenticated payloads into this file.

The authenticated Draft relay reuses this existing lifecycle. It does not create a second refresh-state owner and does not copy reusable auth into the private Draft workflow.

New evidence on 4 September 2026 reopens **operational diagnosis only**, not the authentication architecture: relay run `33901095469` and its single bounded rerun both exchanged refresh state successfully enough to reach frozen `/api/me/` verification, then failed with an unexpected status. Independent static direct-bearer diagnostic rerun `33662138778` reached the same frozen `/api/me/` verifier and failed with the same unexpected-status class while refresh inputs were deliberately blank. Public website monitoring did not establish a broad FPL outage, so the exact HTTP class must be measured rather than guessed.

Because the frozen refresh flow exchanges before `/api/me/` verification and persists the replacement refresh token only after successful identity verification, repeated blind refresh attempts are prohibited while this unexpected-status incident is unresolved. A diagnostic may inspect only status metadata and must not consume refresh state or become a new recovery path.

---

## 6. Private query bridge contract and completed acceptance

### Why the bridge exists

A chat session must be able to answer owner questions without putting manager state in public GitHub and without reconstructing it from memory.

The private repository is the only approved owner-state/query surface. Classic immutable queries and live Draft queries are distinct evidence types but share the same privacy principle.

### Classic `latest` semantics

`latest` does **not** mean newest publication timestamp. The bridge first reads current public production authority and filters candidate private manager releases by exact linked `public_attempt_id`. Publication time can only break ties among authority-correct candidates. If no candidate matches, it fails closed with `REFRESH_REQUIRED`.

Explicit historical `run_id` requests directly resolve that immutable attempt, subject to integrity checks.

### Classic integrity contract

The accepted bridge verifies immutable private manager release, GitHub release-asset digests, Apex private attestations, tag/payload season/run identity, public-attempt linkage, entry `63984`, exact 15-player TeamState, bank/FT/prices/chips/transfers, no `private-auth` query read and narrow allowlisted output.

### Draft query contract

The Draft query is live Official Draft evidence rather than a Classic immutable serving release.

For current roster/market questions:

- use the current private Draft query artifact;
- require exact configured league/entry identity and complete 15-player roster;
- use available/locked rows from that same retrieval;
- never reconstruct from memory or screenshots.

For authenticated transaction evidence:

- use `OPS-008` plus private `PRIV-009` evidence;
- stable private issue #11 is the deterministic fresh-session receipt for the latest revalidated credential-free snapshot;
- result-bearing rows are resolved transaction history and must not be called pending;
- missing/empty result rows are only `unresolved` until exact pending/open semantics are runtime-proven;
- a successful transaction-history endpoint with zero rows does not by itself prove there are no open waivers unless that endpoint/current-state semantic has been established;
- missing/auth-required/auth-rejected/endpoint-failed evidence is **not** an empty queue;
- Draft↔Classic projection joins use name + club + position, never raw numeric ID equality.

Detailed procedure: `docs/APEX_DRAFT_QUERY.md`.

---

## 7. Production constitution — closed decisions

These are constraints unless a separately evidenced governance change deliberately supersedes them.

### Factual authority

Official FPL is authoritative for player identity/element ID, club, FPL position, price/status/availability, fixtures/deadlines and exact manager mechanics when authenticated. Official FPL Draft is the live authority for the configured Draft league roster/ownership/availability/transaction state.

### Serving forecasts

AIrsenal is current production champion and sole serving provider H1–H8. Shadow/challenger disagreement is diagnostic/research evidence only unless promoted through explicit governance. Draft query state does not change serving forecasts.

### Research isolation

- no silent fallback;
- no model voting into production;
- no arbitrary blend;
- no automatic challenger promotion;
- `research.production_influence = NONE`;
- no hindsight/backfilled prospective evidence.

### Solve mechanics

- one frozen snapshot per production attempt;
- no network access during solve;
- exact FPL mechanics;
- provider-blind legal optimisation after forecast acquisition;
- max-EV primary policy;
- one canonical recommendation;
- immutable public/private persistence with run identity/provenance.

### Privacy

Public releases must not contain manager-private squad state, exact commitments, credentials, authenticated Draft owner transaction rows or unfiltered private provider material. Private-auth releases are never query data. Schema-only Draft diagnostics may expose key names/types/counts/sample field names but never authenticated owner scalar values. Owner-auth incident diagnostics may expose only HTTP status code/class and configured transport count/mode labels; they must not read or emit response bodies/headers or credential values.

### Frozen engine separation

`frozen_engine_sha` is immutable forensic lineage. `production_core_sha` is the independently promoted serving pointer. Never update or merge PR #90 to promote production.

---

## 8. Repository architecture and important surfaces

### Documentation constitution

Canonical public documentation surfaces have separated responsibilities:

- `docs/APEX_V2_AUTHORITY.json` — machine serving authority;
- `docs/FPL_APEX_MASTER_STATE.md` — human continuity/evidence ledger;
- `docs/APEX_CAPABILITY_REGISTRY.yaml` — semantic capability/change-surface index, not serving authority;
- `docs/APEX_ARCHITECTURE.md` — single current cross-repository V2 system map;
- `docs/APEX_DECISION_INDEX.yaml` — machine-readable decision status/supersession;
- `docs/APEX_DECISIONS.md` — append-only rationale/history;
- `docs/APEX_DRAFT_QUERY.md` — governed FPL Draft owner-query/relay runbook.

`docs/ARCHITECTURE.md` and `docs/APEX_CANONICAL_DECISION_POLICY.md` are historical/non-serving. Do not create a second current architecture map, second semantic registry or separate prose runbook index.

### Public control plane (`fpl-apex`)

Primary live surfaces include machine authority, canonical production, auth keepalive, deadline watch, evaluation/research, Apex CI/Ops Contract and semantic governance. Draft-specific additions are:

- `.github/workflows/apex-v2-draft-auth-relay.yml` — authenticated read-only Draft transaction relay plus failure-only owner endpoint status diagnostic;
- `scripts/apex_v2_draft_auth_relay_ops.py` — credential-stripping relay controller plus bounded schema-only authenticated diagnostics;
- `docs/APEX_DRAFT_QUERY.md` — Draft owner-query runbook.

The Draft relay is not a serving production workflow. It shares auth concurrency but cannot solve, publish or submit Draft transactions. Its post-auth-failure status probe cannot certify or recover authentication.

### Private persistence/query plane (`fpl`)

Key surfaces include Classic manager/provider persistence/query, plus:

- `apex-query/draft_request.json` — Draft roster/pool request;
- `tools/apex_draft_query.py` — live public Official Draft query;
- `tools/apex_draft_relay_ingest.py` — authenticated relay validator;
- `tools/apex_draft_issue_publish.py` — revalidating stable private receipt publisher;
- `.github/workflows/apex-draft-query.yml` — live Draft query and repository-dispatch receiver;
- private issue #11 — stable machine-managed latest authenticated Draft receipt;
- short-retention private Draft query/auth artifacts;
- `fpl-apex-private-mac` — dedicated repository-level self-hosted execution surface.

Public registry `PRIV-*` capabilities document these boundaries semantically. There is no second private semantic registry.

---

## 9. Project history — compressed durable engineering lineage

GitHub remains the exact per-commit/per-PR archive. This section prevents settled work being rediscovered as a blank-slate design task.

### Era A — V1 foundations and Project Brain (#1–#25)

Early work repaired AIrsenal horizons/refresh, Pinnacle/Elite robustness, production-readiness gates, canonical baselines, diagnostics, replay foundations, evidence semantics and answer/query policy. PR #7 created Project Brain v1.0 and the first mandatory read-before-work protocol.

### Era B — sealed decisions, exact mechanics and evidence correctness (#26–#44)

This era introduced sealed decision bundles, retired duplicate publication paths, hardened missing-evidence behavior, exact FPL mechanics, authoritative evidence ingestion, no-hindsight replay, publication integrity, fail-closed behavior, core-refresh controls and AIrsenal horizon/fixture handling.

### Era C — max-EV, projection semantics and transfer-aware planning (#45–#65)

Key decisions included max-EV-first selection, projection truth/calibration experiments, explicit retirement of failed shrinkage variants, transfer-aware multi-week paths, Understat research, role evidence, zero-minute semantics, GW1-first/receding-horizon planning and a V1 architecture freeze.

### Era D — pre-clean-room V2 exploration (#67–#89)

A sequence of V2 slices explored acquisition, projections, optimisation, persistence, governance and operations. These are historical/research lineage, not current serving authority.

### Era E — clean-room V2 freeze and champion/challenger constitution (#90–#96)

- #90 established clean-room production architecture and remains the permanent frozen lineage anchor; draft/open/unmerged.
- #91 integrated champion–challenger prospective tournament logic.
- #92 added Apex proprietary shadow behavior.
- #94 activated frozen V2 daily operations on `main`.
- #95–#96 added initial FPL Draft availability/ownership support without changing Classic serving authority.

### Era F — authentication and production operations (#97–#110)

This work recovered authenticated owner state, added keepalive/direct diagnostics, safe deadline watching, owner brief/decision-quality operations, shadow-provider reliability and prospective-tournament hardening.

### Era G — decision-edge research and runtime engineering (#111–#114)

Sequential specialist learning and the private Decision Quality lab were added. Heavy independent tasks became parallel/resumable while preserving serving semantics.

### Era H — authority reconciliation and serving-core separation (#115–#123)

Repository documentation/operations were reconciled to V2 authority. #122 separated immutable `frozen_engine_sha` from movable `production_core_sha`; #123 performed the first hardened successor promotion without touching the frozen PR.

### Era I — reproducibility, deterministic promotion and owner-query foundations (#124–#137)

Replay portability, reproducibility investigations, canaries, deterministic successor promotion, snapshot-clock repair, auth recovery, private decision-lab provenance and integration validation were hardened.

### Era J — final production closure and single-solve repair (#138–#149)

Temporary production dispatches isolated defects. #146 permanently eliminated duplicate production optimisation and made publication witness-only. #147 promoted exact core `c0ae9f6e…`. Production run #9 succeeded. #149 restored normal Deadline Watch.

### Era K — continuity and private-query operational closure (#150 public; private #4–#8)

Public PR #150 established the canonical continuity ledger and same-change enforcement. Private PRs #4–#8 established zero-cost self-hosted private execution, exact/latest strategy querying, public-registry binding and current provider-query closure.

### Era L — capability/documentation constitution and private binding closure

Public PR #151 added the single semantic capability registry and decision index, repurposed `APEX_ARCHITECTURE.md` as the current cross-repository map, added semantic CI enforcement and merged with exact-head/post-merge green evidence. Private PR #7 then consumed/validated the public `PRIV-*` bindings without creating a second registry. Public PR #152 closed the final documentation loop.

### Era M — Draft fresh-session owner query, authenticated relay and open-waiver semantic hardening

- private PR #9 merged the governed live Draft roster/available/locked query and runtime-proved exact current state in `33889278311`;
- that runtime isolated entry-specific transactions as auth-required rather than a broken Draft connection;
- private PR #10 added/accepted the credential-free authenticated relay receiver and merged at `e215785fdfecd37cee967ffec9a66cf45e6e9d85`;
- public PR #154 merged the governed `OPS-008` authenticated relay and `PRIV-009` semantics at `4a37729b7cf38a72a48a511fbeb60c7decb89af4` after exact-head public gates passed;
- private PR #12 merged the stable private issue-#11 query target, revalidation publisher, mandatory `PRIV-009` binding and isolated event-class concurrency at `e089b31be4bea257a27964fd52951822d68dc324`;
- public relay `33897685281` → private dispatch `33898312773` runtime-proved authenticated acquisition, credential-free relay, private artifact and stable receipt publication;
- inspection proved the first four result-bearing event-3 rows are resolved transaction history, not a current open queue;
- public PR #155 merged resolved/unresolved classification plus schema-only authenticated `my-team` discovery at `a533a9bcd25699f0f9fe444f11487ac271923471` after exact-head public gates passed;
- its first merged relay and one bounded rerun exposed a new frozen owner-auth unexpected-status incident before Draft acquisition;
- independent static direct-bearer diagnosis reproduced the same unexpected-status class, so bounded status-only upstream diagnosis now precedes further open-waiver semantic work.

---

## 10. Known traps — future agents must not repeat these loops

1. **Do not rebuild the current Classic or Draft squad from old chats/screenshots.** Query owner-private state.
2. **Do not treat publication timestamp as `latest` Classic authority.** Exact public-attempt linkage comes first.
3. **Do not merge or advance PR #90.** Production promotion uses `production_core_sha`.
4. **Do not rerun the optimiser in publication.** Publication is deterministic witness verification.
5. **Do not restore multi-candidate search to production by changing reusable research defaults.** Production explicitly selects one candidate.
6. **Do not interpret historical zero-step GitHub Actions billing rejections as query-code failures.** Those are closed provenance.
7. **Do not switch private workflows back to billable hosted runners.** `fpl-apex-private-mac` is the intended zero-cost private execution surface.
8. **Do not weaken deterministic replay/certification to make a failing run pass.** Diagnose provenance/mechanics instead.
9. **Do not let shadow providers influence serving output implicitly.** They are prospective evidence only.
10. **Do not backfill prospective evidence after outcomes.** No hindsight.
11. **Do not resurrect archived legacy publishers.** Archive is forensic only.
12. **Do not put private manager payloads, Draft owner transactions or credentials into public docs/releases/artifacts/logs.**
13. **Do not create another competing master document.** Update this ledger and machine authority/supporting docs as appropriate.
14. **Do not create a competing capability registry, current system map or prose runbook index.**
15. **Do not copy movable serving/current state into the capability registry or architecture map.** Reference authority instead.
16. **Do not leave state-changing code undocumented.** CI requires this ledger to move with substantive changes.
17. **Do not create an active workflow or `scripts/apex_v2_*.py` surface without registering its capability.**
18. **Do not reopen exact/latest strategy-query acceptance without a new reproducible defect or authority change.**
19. **Do not launch production-core helpers from the mutable control-plane root when they resolve repo-relative core inputs.**
20. **Do not describe result-bearing Draft transaction rows as pending/open waivers.** They are resolved history unless exact upstream semantics prove otherwise.
21. **Do not treat `auth_required`, missing relay evidence, a failed authenticated Draft endpoint, ambiguous unresolved semantics or an unproven empty transaction-history list as “no pending waivers.”**
22. **Do not copy FPL credentials into the private Draft workflow.** The public governed auth owner must relay only a credential-free allowlist.
23. **Do not assume Draft and Classic element IDs are equal.** Reconcile name + club + position.
24. **Do not submit a test waiver/free-agent/trade merely to manufacture semantic evidence.** No Draft write capability exists; discovery remains read-only unless an explicit governed write capability is separately authorized.
25. **Do not repeatedly rerun refresh authentication after an unclassified owner `/api/me/` status.** Refresh exchange precedes identity verification; diagnose the upstream status safely before consuming more attempts.
26. **Do not treat the status-only direct probe as authentication or recovery.** It may report only transport/status metadata and cannot unlock manager or Draft state.

---

## 11. Next actions — diagnose owner auth, then resume exact open/pending Draft semantics

The serving production and Classic owner-query system remain historically accepted. Draft live roster/pool access, prior governed authentication, transaction-history relay, private artifact and stable connected-session receipt are accepted. Current authenticated semantic discovery is blocked by the new Official FPL owner `/api/me/` unexpected-status incident.

Immediate bounded closure:

1. exact-head test and document `agent/auth-owner-me-status-diagnostic`;
2. merge only after Apex CI and Apex V2 Ops Contract are green on the exact head and no authority/provider/PR #90 drift exists;
3. let the merged `OPS-008` push run fail closed if owner auth remains unhealthy, while its post-failure direct probe records only the exact HTTP status/class;
4. classify the incident from that evidence — e.g. rate limiting, upstream 5xx, other 4xx/redirect or network error — without guessing and without reading a response body;
5. repair or wait out the exact proven upstream condition using the existing authentication constitution; do not introduce silent fallback or repeated blind refresh attempts;
6. require a fresh certified owner-auth success before resuming Draft authenticated discovery;
7. run the merged schema-safe `my-team` diagnostic and inspect resolved/unresolved transaction counts;
8. if `my-team` exposes a distinct waiver/request/pending list, implement an explicit allowlisted extractor for that proven list; if it does not, continue only with bounded authenticated GET discovery and do not guess;
9. update the private relay contract/stable issue only after the exact current-request surface is proven;
10. inspect a resulting current pending/open queue, or a proven empty queue from that exact current-request surface;
11. rerun private public-capability binding validation and record exact final acceptance in public/private continuity docs;
12. only then call the Draft connection **CERTIFIED COMPLETE** for fresh-session roster, market and pending/open waiver queries and provide the owner the final Project-instruction block.

Separately, Dastan remains a non-serving runtime-health item after PR #153; its current shadow health can be verified independently without blocking the Draft owner-query closure or changing AIrsenal serving authority.

Normal operations remain: keep the private runner healthy, keep Deadline Watch/auth/production workflows healthy, obtain fresh Official FPL/provider state each deadline, use private `latest` for Classic owner retrieval, keep research non-serving, keep PR #90 frozen and update this ledger whenever substantive state changes.

---

## 12. Change-control protocol for all future work

Every substantive repository change must answer, in this ledger or the private companion as appropriate:

- **What changed?**
- **Why?**
- **Which `Apex-Capabilities` does it affect?**
- **Which authority/invariant does it affect?**
- **What exact tests/CI/release evidence prove it?**
- **What did not change?**
- **What is the new next action, if any?**
- **Does a previously closed decision need to be reopened? If yes, what new evidence justifies that?**

### Capability declaration rule

Public PRs declare machine-readable semantic metadata:

- `Apex-Capabilities: <comma-separated registry IDs>`;
- `Apex-Authority-Changed: yes|no`;
- `Apex-Invariants-Changed: <description|none>`;
- `Apex-Decisions-Reopened: <IDs|none>`.

`scripts/check_capability_registry.py` compares those declarations with actual registered change surfaces; it is not a checkbox-only convention.

### Same-change rule

If any tracked public repository file changes, `docs/FPL_APEX_MASTER_STATE.md` must also change in the same PR/commit, except when the only changed tracked file is the master state itself. The CI guard implements this mechanically.

For the private repo, its analogous companion/CI rule applies.

### Master-state/registry edits are not authority promotions

Editing this file, the capability registry, decision index, Draft runbook or architecture map cannot promote a serving core, merge the frozen engine, change provider authorization, publish an attempt or establish a Classic manager decision. Those require their existing machine/release/governance mechanisms.

---

## 13. Changelog for this ledger

### 2026-09-04 — owner-auth unexpected-status incident isolated and bounded

- public PR #155 exact head `9315fa90ba1c23bfaf8c4a51c281aea73fa6e1f2` passed Apex CI `33899930858` and Ops Contract `33899930818` and merged at `a533a9bcd25699f0f9fe444f11487ac271923471`;
- merged Draft relay `33901095469` failed before any Draft request because frozen Official FPL owner `/api/me/` verification returned an unexpected non-200/non-401/non-403 status;
- one bounded rerun reproduced the same failure and blind refresh retries stopped;
- historical non-serving direct-auth workflow run `33662138778` was rerun with current static bearer and refresh disabled; it independently reproduced the same frozen `/api/me/` unexpected-status class;
- current diagnostic branch adds only failure-gated streamed status-code/class reporting, reads no body/headers, exposes no credentials and cannot recover auth or unlock Draft querying;
- refresh/auth recovery semantics, machine authority, AIrsenal serving, frozen PR #90, private owner surfaces and Draft no-write policy are unchanged.

### 2026-09-04 — authenticated Draft connection accepted; open-waiver semantics hardened

- public PR #154 exact head `10728ba721e325639a71e4e998960c9c32a49fde` passed Apex CI `33896311945` and Ops Contract `33896311949` and merged at `4a37729b7cf38a72a48a511fbeb60c7decb89af4`;
- merged public `OPS-008` successfully acquired certified owner authentication, queried Official Draft entry transactions and dispatched a credential-free relay privately;
- private PR #12 exact head `6c7eedb301958dff79d26be9363db3f96b76b7dc` passed Draft run `33897979229` and private master/public-capability contract `33897979355` and merged at `e089b31be4bea257a27964fd52951822d68dc324`;
- private PR #12 added stable private issue #11 plus a revalidation publisher and corrected Draft event-class concurrency so PR/schedule/dispatch runs wait rather than cancel one another;
- fresh public relay `33897685281` produced current-private repository dispatch `33898312773`, whose relay validator, artifact upload and stable issue publisher all succeeded;
- artifact `9946749382`, digest `sha256:4d2b41366c350eb96042cdd6037d660c5d0828139cd4d8722416eaaca6a503b1`, proves the private credential-free path;
- first stable receipt contained four event-3 waiver rows with non-empty result codes and therefore demonstrated processed transaction history rather than a certified current open queue;
- PR #155 added resolved/unresolved classification plus schema-only authenticated `my-team` discovery; no owner scalar values, credentials or Draft writes were exposed;
- machine authority, AIrsenal serving, frozen PR #90, Classic owner state, optimiser/research semantics and billing policy remain unchanged.

### 2026-09-04 — governed FPL Draft fresh-session query and authenticated relay staged

- private PR #9 merged at `6474254554b3b5f2500fdad2005ee90fb7c0656f` and post-merge Draft run `33889278311` proved exact 15-player roster, 478 available, 24 locked and healthy public Draft history while correctly reporting entry transactions `auth_required`;
- private PR #10 exact head `8dcef5e3c961e5fe3408a523526db1b0ec3f942f` passed Draft query run `33892177717` and master-state contract `33892177813` and merged at `e215785fdfecd37cee967ffec9a66cf45e6e9d85`;
- PR #10 receiver accepts only credential-free `apex-private-draft-auth-relay-v1` repository dispatches and stores a seven-day private artifact on the self-hosted Mac;
- public branch `agent/draft-auth-relay` added the existing-auth-backed Draft transaction producer, workflow, adversarial tests and `docs/APEX_DRAFT_QUERY.md`;
- capability registry added `OPS-008` authenticated Draft transaction relay and `PRIV-009` live FPL Draft owner query; `INT-001` depends on `PRIV-009`;
- ChatGPT policy and architecture explicitly route fresh Draft questions through this governed path rather than screenshots/chat memory;
- machine authority, production core, AIrsenal serving role, frozen PR #90, Classic owner state, optimiser/research semantics and billing policy were unchanged.

### 2026-09-04 — current-provider query fixed; Dastan core-root repair merged

- private PR #8 repaired the narrow projection request and its exact-head/post-merge checks passed;
- canonical production diagnostic proved Dastan failure came from repo-root orchestration while serving production remained valid;
- bounded public PR #153 repaired Dastan core-root execution and merged at `adf7c22058ef9b384793fabdad6853259d23a648`;
- machine authority, AIrsenal serving, Dastan shadow-only status, PR #90, owner state and billing/spend were unchanged.

### 2026-09-04 — documentation/continuity constitution closed

- public PR #151 exact-head Apex CI `33873835393` and Apex V2 Ops Contract `33873835399` passed;
- PR #151 merged as `6a1509f766e6438a43d296e8e900518a18967959` and post-merge Apex CI `33874537255` passed;
- private PR #7 consumed/validated the single public `PRIV-*` capability semantics without creating a second registry;
- private PR #7 final exact-head contract `33876581770` passed and merged at `459427fe1e90565d61f8a9f6547f3876c4f3ec9a`;
- public PR #152 passed its exact-head gates and merged at `620ad5d305008c018c9ea3ccd887c9de8b510b9c`;
- machine authority and spending/billing policy were unchanged.

### 2026-09-04 — APEX OPERATIONAL closure

- private self-hosted runner `fpl-apex-private-mac` registered and accepted without spending-limit changes;
- exact strategy query run `33868412431` passed;
- authority-selected `latest` strategy query `33868662109` passed;
- exact and latest JSON were byte-identical at SHA-256 `e50c4ebde19a2c68bfa4c38f33a6dd81f1d0922851f1e932bae522a898609d60`;
- both resolved immutable run `33850307770-1`, entry `63984`, exact 15-player owner state, £0.5m bank, 1 FT and complete transfer prices/state;
- final private contract `33868662187` passed;
- public authority remained core `c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437` with frozen PR #90 unchanged.

### 2026-09-04 — master continuity control layer introduced

- consolidated live production closure state after successful immutable run `33850307770-1`;
- documented permanent PR #146 single-solve/publication-witness repair and #147 promotion;
- recorded authentication recovery and successful release evidence;
- reconciled older Project Brain documents into one canonical human continuity ledger;
- added mandatory agent startup instructions and same-change CI enforcement;
- preserved machine authority and immutable release evidence above prose in the precedence hierarchy.
