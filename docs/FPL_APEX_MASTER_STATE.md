# FPL Apex — Canonical Master State

> **MANDATORY CONTINUITY FILE — READ BEFORE ANY SUBSTANTIVE WORK**
>
> This is the canonical **human/project continuity ledger** for FPL Apex. It exists so a fresh ChatGPT, Codex, Claude, human maintainer, or CI operator can recover the project without relying on conversation memory.
>
> It does **not** replace machine authority or immutable evidence. Where this prose conflicts with machine-verifiable state, the precedence rules below apply and this file must be corrected in the same change that discovers the conflict.

**Ledger schema:** 1  
**State snapshot:** 5 September 2026, after PR #160 merged the PITCHSIDE predeadline-recovery repair and the project committed price-aware receding-horizon transfer planning as a required production-core successor destination under D033
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

The serving production chain and accepted Classic owner-private query chain have completed their required acceptance. The live FPL Draft roster/market connection and authenticated transaction relay are also historically runtime-proven. One narrower Draft claim remains deliberately uncertified: the exact **current open/pending waiver-request semantics**. The first authenticated stable receipt proved that the known entry transaction endpoint includes processed history, so resolved history must not be mislabeled as the current open queue.

The 4 September owner-auth incident is no longer a credential mystery. Public PR #156 classified the exhausted prior credentials as rotating refresh rejected, bootstrap refresh rejected and static bearer `/api/me/` HTTP 401/rejected. Public PR #157 then merged the permanent two-phase rotation durability repair: exact head `e0a0f5c4a62f07ef10ad17f544bd7b08b63f19f7` passed Apex CI `33911107334` and Apex V2 Ops Contract `33911107378`; merge commit/current accepted public baseline for that repair is `1219861f3b9c3d707f6c80f94fa6f26325bab4a1`. Machine authority, AIrsenal serving H1–H8 and frozen PR #90 were unchanged.

After #157 merged, one fresh browser-issued refresh credential was re-seeded directly into the approved GitHub Actions secret without entering chat. Keepalive rerun attempt 2, job `101151219540` on run `33911608442`, proved the new credential itself is valid: the old rotating private refresh was rejected, bounded bootstrap recovery successfully exchanged the newly re-seeded refresh credential, the rotated child was durably staged, and execution advanced through exact manager verification to immutable-activation code. It then failed with `RefreshRotationIndeterminate: Verified staged FPL refresh child disappeared before immutable activation` because same-run activation immediately tried to rediscover the just-created private draft through GitHub's eventually-consistent release listing.

That failure did **not** require another token. PR #158, **Fix same-run FPL refresh draft activation race**, merged at `8efaa70b1172b0a0c6d20357d5d528a5a65ac8b7` from exact head `4528715a625adc94a60a249e1fb4df42c5811bae` after Apex CI `33913733476` and Apex V2 Ops Contract `33913733468` passed. Same-run activation now uses the exact staged release ID/upload digests; cross-run recovery remains list + re-download/decrypt based. Any remaining auth health claim must come from fresh runtime evidence rather than the pre-merge failure.

Canonical production run `33850307770-1` remains the accepted serving proof. AIrsenal remains sole serving provider H1–H8. Dastan and PITCHSIDE remain research-only. The GW3 PITCHSIDE recoverability defect is now closed in code by PR #160: exact head `f7b67d0a79acef82ee4fa0b0b858a207810f5521` passed Apex CI `33927262385` and Apex V2 Ops Contract `33927262342`, then merged at `4e02c315509f41865198dd3cc1ea6098c5bd2f73`. Materially changed predeadline PITCHSIDE evidence can now create a content-addressed reseal for the same immutable production run, the hourly schedule participates in resealing, unchanged evidence stays idempotent, and canonical selection uses latest valid `tournament_sealed_at`. Production authority, optimiser semantics, research influence, no-hindsight and frozen PR #90 remain unchanged.

A separate manager-decision architecture decision is now explicit under D033: Apex's primary product is the owner transfer/squad-management decision, not projection tables. Price-aware receding-horizon transfer planning is a required production-core successor destination. Any research/shadow/canary implementation is temporary certification evidence only; it is not an acceptable permanent terminal state. This documentation decision does **not** change current machine authority or production output. Implementation and promotion remain separately gated.

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

### FPL Draft owner-query closure — connection/relay accepted; current auth and exact open-waiver semantics still gated

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
- `PRIV-009` live FPL Draft owner query registered;
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
- merge commit: `a533a9bcd25699f0f9fe444f11487ac271923471`;
- transaction rows are classified as `resolved` when upstream `result` is non-empty and `unresolved` when it is absent/empty;
- `unresolved` is deliberately not renamed `pending` until runtime evidence proves that exact relationship;
- authenticated `entry/<live_team_entry_id>/my-team` is queried only for a schema-only diagnostic;
- the diagnostic may expose key names, container types, list counts and sample field names for transaction/waiver/request/pending/trade-like paths, but never owner scalar values;
- no Draft POST/DELETE/write path was introduced.

Immediately after PR #155 merged, relay `33901095469` failed before any Draft endpoint at `Acquire certified owner credential`; one bounded rerun reproduced the failure. Public PR #156 then added only a status-only diagnostic. Its exact head `174790f7cea7d0b2f235f0a607630d0c974b76a9` passed Apex CI `33902899716` and Apex V2 Ops Contract `33902899673` and merged at `cd5bd12eda187c372b8d389260768667d0e26234`.

Merged scheduled relay run `33908393271` provides the accepted incident classification:

- private auth-store preflight: passed;
- rotating refresh exchange: rejected/expired;
- configured bootstrap refresh exchange: rejected/expired;
- direct owner recovery: rejected;
- failure-only direct status probe: **HTTP 401 / `rejected`** for bearer;
- diagnostic response body read: false;
- Draft transaction query/dispatch: skipped;
- frozen worktree integrity: passed.

PR #157 then permanently moved rotation durability ahead of manager verification and aligned Keepalive/Draft Relay to authority-selected production-core auth primitives. Exact head `e0a0f5c4a62f07ef10ad17f544bd7b08b63f19f7` passed Apex CI `33911107334` and Ops Contract `33911107378`, then merged at `1219861f3b9c3d707f6c80f94fa6f26325bab4a1`.

After a fresh browser refresh re-seed, Keepalive rerun job `101151219540` proved the new bootstrap credential exchanged successfully and exact manager verification completed. It failed only at immediate post-verification activation because `_activate_staged_rotation` re-listed releases and did not yet see the just-created private draft. The new child remains staged private recovery evidence; no fallback was attempted and the authority core stayed untouched.

PR #158 removed that eventual-consistency dependency by retaining the exact private draft release ID plus upload SHA-256 map from staging and using those values for same-run activation. Recovery from a prior process/run continues to use authenticated draft listing and re-download/decryption. Wrong-manager same-run state is purged by exact release ID. This is an activation-race correction inside the already accepted two-phase design, not a new auth architecture.

**Do not call current pending/open waiver retrieval certified yet.** Historical connection/relay/private receipt evidence remains valid. Current certification still requires fresh runtime evidence after the merged auth repair plus exact `my-team`/open-waiver semantic discovery.

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
- PR #154, **Complete governed FPL Draft authenticated owner-query relay**, merged at `4a37729b7cf38a72a48a511fbeb60c7decb89af4` after exact-head Apex CI `33896311945` and Ops Contract `33896311949` passed;
- PR #155, **Harden FPL Draft open-waiver semantics**, merged at `a533a9bcd25699f0f9fe444f11487ac271923471` after exact-head Apex CI `33899930858` and Ops Contract `33899930818` passed;
- PR #156, **Diagnose unexpected Official FPL owner status safely**, exact head `174790f7cea7d0b2f235f0a607630d0c974b76a9`, passed Apex CI `33902899716` and Ops Contract `33902899673`, merged at `cd5bd12eda187c372b8d389260768667d0e26234`;
- PR #157, **Harden FPL owner-auth refresh rotation durability**, exact head `e0a0f5c4a62f07ef10ad17f544bd7b08b63f19f7`, passed Apex CI `33911107334` and Ops Contract `33911107378`, merged at `1219861f3b9c3d707f6c80f94fa6f26325bab4a1`;
- fresh browser re-seed acceptance attempt: Keepalive run `33911608442`, attempt-2 job `101151219540`, reached verified staged-child activation and failed only on immediate release-list rediscovery;
- PR #158, **Fix same-run FPL refresh draft activation race**, exact head `4528715a625adc94a60a249e1fb4df42c5811bae`, passed Apex CI `33913733476` and Ops Contract `33913733468`, merged at `8efaa70b1172b0a0c6d20357d5d528a5a65ac8b7`;
- PR #160, **Fix PITCHSIDE predeadline tournament recovery**, exact head `f7b67d0a79acef82ee4fa0b0b858a207810f5521`, passed Apex CI `33927262385` and Apex V2 Ops Contract `33927262342`, merged at current public `main` `4e02c315509f41865198dd3cc1ea6098c5bd2f73`;
- protected control plane; historical ruleset identifier `21759706` — verify live before relying on it.

### Machine authority

`docs/APEX_V2_AUTHORITY.json` was re-read before this transfer-policy architecture decision and remains unchanged:

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

The transfer-policy architecture decision and PR #160 research-operations repair do not change machine authority.

### Frozen PR #90

PR #90, **Build Apex V2 clean-room production architecture**, remains deliberately open, draft, unmerged, not an operations branch and not a branch to advance as part of successor promotion.

The immutable authority anchor is forensic SHA `99cc7b51b0cff45462b567084cb1844cfe0a456f`. The policy remains **NEVER_MERGE_OR_ADVANCE**. A mutable PR branch head is not authority and must never replace this SHA in continuity or runtime decisions.

### Private repository

- repository: `mcnuggets651/fpl`;
- accepted final-latest merge commit: `a310450fd27aa469eac9ae91971334925b4bee77`;
- private capability/documentation binding PR #7 merged at `459427fe1e90565d61f8a9f6547f3876c4f3ec9a`;
- current-provider query PR #8 merged at `2f4ac141224f1fe222de6893a544abfbf685ea6a`;
- live Draft query PR #9 merged at `6474254554b3b5f2500fdad2005ee90fb7c0656f`; post-merge Draft query `33889278311`: success;
- authenticated Draft relay receiver PR #10 merged at `e215785fdfecd37cee967ffec9a66cf45e6e9d85` after exact-head Draft query `33892177717` and private master contract `33892177813` succeeded;
- stable connected-session Draft surface PR #12 merged at current private baseline `e089b31be4bea257a27964fd52951822d68dc324` after exact-head Draft run `33897979229` and private master/public-capability contract `33897979355` succeeded;
- current accepted repository-dispatch `33898312773` successfully validated the last healthy authenticated relay, uploaded artifact `9946749382` and published stable private issue #11;
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

## 5. Authentication recovery — valid browser re-seed; exact-ID activation race is the only current auth blocker

Before production run #8, stored FPL tokens expired. A fresh authenticated FPL browser session renewed the encrypted Actions secret; auth keepalive `33850189866` then passed private-store preflight, credential rotation, private persistence and frozen-worktree integrity. That historical recovery was valid and supported the accepted production run.

The authenticated Draft relay reuses this same owner-auth lifecycle. It does not create a second refresh-state owner and does not copy reusable auth into the private Draft workflow.

On 4 September 2026 the previous credential set expired. PR #156 and merged relay run `33908393271` provided exact evidence: newest rotating private refresh rejected at exchange, configured bootstrap refresh rejected at exchange, static bearer `/api/me/` HTTP 401/rejected, no cookie configured, Draft acquisition skipped and diagnostic body unread.

PR #157 then closed the exchange-before-durable-child defect. It merged at `1219861f3b9c3d707f6c80f94fa6f26325bab4a1` after Apex CI `33911107334` and Ops Contract `33911107378` passed. Production, Keepalive and Draft Relay now use the authority-selected core auth primitives under one serialized two-phase controller: recover an existing staged child first; exchange once; encrypt/upload the child privately before `/api/me/`; treat it as inactive recovery evidence; verify entry `63984`; activate only after exact match; prohibit fallback for an indeterminate post-exchange state; purge wrong-manager staged state.

The owner then re-seeded `FPL_REFRESH_TOKEN` once with a fresh browser-issued refresh token directly in GitHub Actions. Keepalive run `33911608442` attempt-2 job `101151219540` is the accepted proof that this credential is valid: the bootstrap exchange succeeded, a rotated child was staged, manager verification succeeded, and the workflow reached activation. It failed only because same-run activation tried to rediscover the newly created draft via `list_releases()` and received no immediate match. The child was not discarded or exposed; fail-closed behavior preserved it as private staged recovery evidence.

PR #158 removed that eventual-consistency dependency:

1. `_stage_refresh_rotation` returns the exact GitHub draft release ID and upload SHA-256 map together with its tag;
2. after exact manager match, same-run activation passes that exact release ID/map to the existing private-store `_publish_draft`, which verifies the release asset set and GitHub SHA-256 digests before immutable publication;
3. process-loss recovery still discovers staged children through authenticated private release listing and re-downloads/decrypts/validates them before recovering forward;
4. same-run wrong-manager state is deleted using the exact returned release ID, while recovered wrong-manager state retains strict list-based purge;
5. regression tests model a draft that exists by ID but is invisible to `list_releases()` and require both matched-owner activation and wrong-manager purge to succeed.

Do **not** request another browser token merely because attempt 2 failed activation. The evidence proves the submitted credential was valid and generated a staged child. Ask for another re-seed only if fresh governed runtime evidence proves the existing staged child/credential path is genuinely unrecoverable.

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

### Manager-decision objective

Apex's owner-facing product is the legal squad-management decision. Forecasts are inputs to that decision. Receding-horizon transfer planning must compare ROLL against strong legal transfer paths from the exact owner state and carry future optionality rather than merely rank non-owned players by standalone xP.

Price-aware transfer planning is a required future production-core successor capability under D033. Future price uncertainty must alter route feasibility/continuation value only; it must not manufacture fantasy points or add an arbitrary team-value reward. Research/canary operation is transitional certification evidence, not a terminal non-serving home for this capability.

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

Public releases must not contain manager-private squad state, exact commitments, credentials, authenticated Draft owner transaction rows or unfiltered private provider material. Private-auth releases are never query data. Schema-only Draft diagnostics may expose key names/types/counts/sample field names but never authenticated owner scalar values. Owner-auth incident diagnostics may expose only HTTP status code/class and configured transport count/mode labels; they must not read or emit response bodies/headers or credential values. Encrypted staged refresh children remain private drafts and are never active until exact manager identity is verified.

### Frozen engine separation

`frozen_engine_sha` is immutable forensic lineage. `production_core_sha` is the independently promoted serving pointer and the resolver for live production-core auth preflight/config. Never update or merge PR #90 to promote production or to repair authentication.

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

Primary live surfaces include machine authority, canonical production, auth keepalive, deadline watch, evaluation/research, Apex CI/Ops Contract and semantic governance. Authentication/Draft-specific surfaces are:

- `scripts/apex_v2_auth_ops.py` — the one current serialized operations auth transaction controller; it uses authority-selected core auth helpers/config, stages rotated children privately before manager verification and activates same-run drafts by the exact returned release ID/digest map rather than immediate re-listing;
- `.github/workflows/apex-v2-auth-keepalive.yml` — non-serving durable auth maintenance using the same authority-selected core boundary;
- `.github/workflows/apex-v2-draft-auth-relay.yml` — authenticated read-only Draft transaction relay plus failure-only owner endpoint status diagnostic, also using the same auth boundary;
- `scripts/apex_v2_draft_auth_relay_ops.py` — credential-stripping relay controller plus bounded schema-only authenticated diagnostics;
- `docs/APEX_V2_DAILY_OPERATIONS.md` — auth lifecycle and production operations runbook;
- `docs/APEX_DRAFT_QUERY.md` — Draft owner-query runbook.

The Draft relay is not a serving production workflow. It shares auth concurrency but cannot solve, publish or submit Draft transactions. Its post-auth-failure status probe cannot certify or recover authentication. The two-phase auth repair and exact-ID activation correction strengthen durability inside the existing auth boundary; they do not add another auth owner or serving plane.

### Private persistence/query plane (`fpl`)

Key surfaces include Classic manager/provider persistence/query, plus:

- encrypted immutable/private auth releases and temporary encrypted staged rotation drafts used only by public `PROD-002` auth operations;
- `apex-query/draft_request.json` — Draft roster/pool request;
- `tools/apex_draft_query.py` — live public Official Draft query;
- `tools/apex_draft_relay_ingest.py` — authenticated relay validator;
- `tools/apex_draft_issue_publish.py` — revalidating stable private receipt publisher;
- `.github/workflows/apex-draft-query.yml` — live Draft query and repository-dispatch receiver;
- private issue #11 — stable machine-managed latest authenticated Draft receipt;
- short-retention private Draft query/auth artifacts;
- `fpl-apex-private-mac` — dedicated repository-level self-hosted execution surface.

Public registry `PRIV-*` capabilities document these boundaries semantically. There is no second private semantic registry. The private Draft query workflow never receives reusable FPL credentials.

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

### Era M — Draft fresh-session owner query, authenticated relay and auth durability closure

- private PR #9 merged the governed live Draft roster/available/locked query and runtime-proved exact current state in `33889278311`;
- that runtime isolated entry-specific transactions as auth-required rather than a broken Draft connection;
- private PR #10 added/accepted the credential-free authenticated relay receiver and merged at `e215785fdfecd37cee967ffec9a66cf45e6e9d85`;
- public PR #154 merged the governed `OPS-008` authenticated relay and `PRIV-009` semantics at `4a37729b7cf38a72a48a511fbeb60c7decb89af4` after exact-head public gates passed;
- private PR #12 merged the stable private issue-#11 query target, revalidation publisher, mandatory `PRIV-009` binding and isolated event-class concurrency at `e089b31be4bea257a27964fd52951822d68dc324`;
- public relay `33897685281` → private dispatch `33898312773` runtime-proved authenticated acquisition, credential-free relay, private artifact and stable receipt publication;
- inspection proved the first four result-bearing event-3 rows are resolved transaction history, not a current open queue;
- public PR #155 merged resolved/unresolved classification plus schema-only authenticated `my-team` discovery at `a533a9bcd25699f0f9fe444f11487ac271923471` after exact-head public gates passed;
- public PR #156 merged the fail-closed status diagnostic at `cd5bd12eda187c372b8d389260768667d0e26234` and runtime-classified the exhausted prior credentials as rotating/bootstrap rejected plus direct bearer 401/rejected;
- public PR #157 merged the two-phase rotation durability repair at `1219861f3b9c3d707f6c80f94fa6f26325bab4a1` after exact-head Apex CI `33911107334` and Ops Contract `33911107378`;
- a fresh browser refresh re-seed then runtime-proved successful bootstrap exchange, private child staging and exact manager verification in Keepalive job `101151219540`;
- that same run exposed only an eventual-consistency race between just-created draft release ID and immediate `list_releases()` rediscovery before activation;
- PR #158 then removed the same-run list-visibility dependency while preserving list + re-download recovery across runs;
- pending/open-waiver semantics remain deliberately uncertified until fresh auth/current `my-team` semantics are proven and the private fresh-session receipt is revalidated.

### Era N — PITCHSIDE recoverability closure and transfer-policy product commitment

- PR #160 merged the bounded PITCHSIDE predeadline reseal recovery with exact-head Apex CI/Ops Contract green while preserving research-only/no-hindsight boundaries;
- D033 then made the owner transfer/squad-management decision the explicit product objective and made price-aware receding-horizon transfer planning a required production-core successor destination;
- research/shadow/canary execution for the transfer policy is explicitly transitional certification evidence, not an acceptable permanent destination;
- current machine authority, AIrsenal serving role, exact production core and frozen PR #90 remain unchanged until a future certified successor is explicitly promoted.

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
25. **Do not keep probing the already-classified old owner incident.** The previous durable credentials were 401/rejected; the new browser re-seed has already proven valid by successful exchange and manager verification.
26. **Do not treat the status-only direct probe as authentication or recovery.** It may report only transport/status metadata and cannot unlock manager or Draft state.
27. **Do not bind live owner auth to the frozen forensic preflight when machine authority selects a promoted production core.** Resolve live auth preflight/config from `production_core_sha`; use `frozen_engine_sha` only for ancestry/forensics.
28. **Do not exchange a refresh parent and wait until after manager verification to make the child durable.** Stage the encrypted child privately immediately after exchange and before `/api/me/` verification.
29. **Do not retry a consumed refresh parent when a staged child exists.** Recover forward from the staged child under the serialized auth lock.
30. **Do not fall through to bootstrap/direct auth after an indeterminate post-exchange state.** The staged child is the only safe recovery path.
31. **Do not retain staged credentials proven to belong to another manager.** Purge the wrong-manager staged chain or stop for manual private-store cleanup.
32. **Do not ask for another browser re-seed after the accepted 4 September attempt merely because same-run draft activation failed.** The new credential already exchanged and verified the manager; first recover the durable staged child.
33. **Do not make same-run activation depend on immediate `list_releases()` visibility.** Use the exact release ID/upload digests returned by the successful stage call; reserve list + re-download for cross-run recovery.
34. **Do not treat an external-provider DNS as terminal before the deadline.** PITCHSIDE may be re-captured prospectively against the same Official hash and a materially changed source may create a new immutable seal for the same production run.
35. **Do not select repeated external captures by `snapshot_frozen_at`.** Canonical prospective selection is by latest valid `tournament_sealed_at`; the production snapshot timestamp remains immutable evidence, not a reseal clock.
36. **Do not treat standalone player xP rankings as transfer strategy.** Owner decisions must compare legal routes from the exact TeamState, with ROLL as a real candidate and FT/bank/future-path effects carried forward.
37. **Do not permanently park price-aware transfer planning in shadow/research.** Shadow/canary is a promotion gate only. The committed destination is a certified production-core successor, and price movement may change affordability/continuation value but may not manufacture fantasy points.

---

## 11. Next actions — implement the price-aware transfer-policy successor and verify live owner runtime state

The serving production and Classic owner-query system remain accepted. PR #160 has closed the bounded PITCHSIDE predeadline recoverability code defect. Current auth/Draft runtime health must still be established from fresh governed evidence before making new owner-specific claims; do not infer it from historical pre-repair failures.

The primary product-development programme is now D033:

1. specify the successor transfer-policy state contract from the exact current production core: exact TeamState, bank, FT rollover, purchase/selling prices, legal squad mechanics and AIrsenal H1–H8 remain the baseline inputs;
2. add a deterministic, replayable price-transition evidence layer that stores timestamped pre-change inputs and produces calibrated uncertainty for future price movement without reverse-engineering or inventing hidden FPL rules;
3. represent future price uncertainty as route-feasibility scenarios/distributions, not as a synthetic points or team-value bonus;
4. compare ROLL, materially strong one-transfer moves, legal multi-transfer combinations, chained future routes and justified hits by expected continuation value, including route-survival probability, price-out risk, wait regret, information regret, FT option value and policy stability;
5. require zero-price-variance/no-price-change cases to reproduce the existing optimiser semantics, and require exact selling-price/purchase-price/FT/hit/squad-legality mechanics under adversarial tests;
6. keep research/shadow/canary execution strictly transitional and non-serving while collecting prospective predeadline evidence; no hindsight, no automatic promotion and no weakening of privacy/replay/certification gates;
7. once the descendant successor passes exact-head CI, readiness, deterministic replay, adversarial mechanics tests and prospective/canary acceptance, promote only by the existing explicit `production_core_sha` governance path; never merge or advance frozen PR #90;
8. after promotion, extend the private `PRIV-003` strategy query to expose the authority-correct route comparison/timing evidence without solving independently or creating a second authority;
9. update the capability registry only when actual capability ownership, entry points, dependencies, runbooks, tests or change surfaces are introduced/changed; D033 itself does not invent unimplemented capability IDs.

Normal operations remain: keep the private runner healthy, verify current auth/Draft state from governed runtime evidence, keep Deadline Watch/auth/production workflows healthy, obtain fresh Official FPL/provider state each deadline, use private `latest` for Classic owner retrieval, keep research non-serving until explicit promotion, keep PR #90 frozen and update this ledger whenever substantive state changes.

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

### 2026-09-05 — transfer policy committed as required production destination

- D033 records that Apex's primary owner-facing product is the legal transfer/squad-management decision; forecasts are inputs, not the end product;
- `docs/APEX_ARCHITECTURE.md` now makes price-aware receding-horizon transfer planning a required production-core successor destination;
- the successor must compare ROLL and legal transfer paths from exact owner TeamState, preserve exact FT/bank/purchase/selling-price mechanics and quantify route survival, price-out risk, wait/information regret and policy stability where supportable;
- price movement may alter affordability/continuation value but must never create an arbitrary team-value/xP bonus;
- research/shadow/canary execution is explicitly a temporary certification/promotion gate, not an acceptable permanent home for this capability;
- no new unimplemented registry capability was invented: the registry changes only when actual ownership/entry points/dependencies/runbooks/tests/change surfaces change;
- this decision does not change `production_core_sha`, AIrsenal serving authority, current production output, research production influence, private owner state or frozen PR #90.

### 2026-09-05 — master reconciled after PR #160 merge

- PR #160 exact head `f7b67d0a79acef82ee4fa0b0b858a207810f5521` passed Apex CI `33927262385` and Apex V2 Ops Contract `33927262342`;
- PR #160 merged at `4e02c315509f41865198dd3cc1ea6098c5bd2f73`, replacing the stale master statement that PITCHSIDE predeadline recovery was still an active branch;
- materially distinct external evidence can be resealed before deadline against one immutable production run/Official hash, unchanged evidence remains idempotent, the hourly schedule participates, and selection uses latest valid `tournament_sealed_at`;
- AIrsenal serving authority, machine authority, no-hindsight, privacy, OpenFPL readiness policy and frozen PR #90 remain unchanged.

### 2026-09-04 — PITCHSIDE same-run predeadline recovery defect bounded after PR #158 merge

- PR #158 merged at `8efaa70b1172b0a0c6d20357d5d528a5a65ac8b7` from exact head `4528715a625adc94a60a249e1fb4df42c5811bae` after Apex CI `33913733476` and Apex V2 Ops Contract `33913733468` passed, closing the same-run auth draft-list activation code defect;
- GW3 tournament inspection then showed PITCHSIDE could be explicit DNS correctly yet remain unable to recover automatically before deadline because scheduled runs performed maintenance only and the candidate/private supplement namespace was one immutable object per production `run_id`;
- the selector also used `snapshot_frozen_at`, which cannot distinguish repeated external captures against one immutable production snapshot;
- bounded `agent/pitchside-predeadline-recovery` content-addresses materially distinct external evidence, allows the existing hourly schedule to attempt a predeadline reseal, preserves unchanged-byte idempotency and selects by latest valid `tournament_sealed_at`;
- the repair does not rerun production, alter Official hashes, fill missing forecasts, backfill GW3, change AIrsenal serving authority, change machine authority or touch frozen PR #90;
- OpenFPL remains governed by its separate 10-completed-exact-rule-GW readiness policy and is not made artificially eligible by this PITCHSIDE repair.

### 2026-09-04 — two-phase auth merged; valid browser re-seed exposed and bounded same-run activation race

- public PR #157 exact head `e0a0f5c4a62f07ef10ad17f544bd7b08b63f19f7` passed Apex CI `33911107334` and Apex V2 Ops Contract `33911107378` and merged at `1219861f3b9c3d707f6c80f94fa6f26325bab4a1`;
- PR #157 made the rotated child durable before manager verification, aligned Keepalive/Draft Relay with authority-selected core auth primitives, preserved fail-closed post-exchange recovery and left machine/serving authority unchanged;
- the owner then re-seeded `FPL_REFRESH_TOKEN` once directly in GitHub Actions with a fresh browser-issued credential; no credential value entered chat or repository content;
- Keepalive run `33911608442` attempt-2 job `101151219540` proved that new credential exchanged successfully, created a private staged child and passed exact manager verification;
- activation alone failed with `Verified staged FPL refresh child disappeared before immutable activation` because the code immediately re-listed GitHub releases and did not yet observe its just-created draft;
- fail-closed behavior preserved the staged child and did not fall back or retry the consumed parent;
- bounded `agent/auth-stage-activation-race` retains the exact release ID/upload SHA-256 map returned by staging and uses those values for same-run digest-verified immutable activation, while cross-run recovery remains list + re-download/decrypt based;
- adversarial tests model eventual-consistent list visibility for both owner-match activation and wrong-manager purge;
- another browser token must not be requested unless the merged staged-recovery proof itself establishes unrecoverable state;
- AIrsenal serving, research isolation, Draft no-write policy, private owner boundaries, production core and frozen PR #90 remain unchanged.

### 2026-09-04 — owner auth classified 401/rejected; two-phase refresh durability repair prepared

- public PR #156 exact head `174790f7cea7d0b2f235f0a607630d0c974b76a9` passed Apex CI `33902899716` and Apex V2 Ops Contract `33902899673` and merged at `cd5bd12eda187c372b8d389260768667d0e26234`;
- merged scheduled Draft relay `33908393271` failed closed at owner authentication while its failure-only diagnostic succeeded and reported configured bearer `/api/me/` as HTTP `401`, status class `rejected`, with `body_read=false`;
- the same run confirmed rotating private refresh and bootstrap refresh were explicitly rejected, Draft acquisition/dispatch was skipped and frozen worktree integrity passed;
- the incident is therefore credential exhaustion/rejection rather than an unclassified rate-limit/5xx/Draft failure;
- investigation exposed a real prior durability window: refresh exchange could consume the parent before manager verification while the child was not yet durable;
- bounded branch `agent/auth-refresh-two-phase-rotation` staged the encrypted rotated child privately before manager verification, recovered already-staged children through authenticated private release listing, activated only after exact entry `63984` proof, forbade post-exchange fallback and strictly purged wrong-manager staged state;
- Keepalive and Draft Relay were changed to resolve auth preflight/config from machine authority `production_core_sha`, matching Daily Production, while `frozen_engine_sha` remained immutable ancestry/forensic authority;
- adversarial tests modelled draft listing, encrypted asset recovery, digest-verified activation, wrong-manager purge and workflow binding;
- machine authority, AIrsenal serving, research influence, Draft no-write policy, private owner-state boundaries, billing policy and frozen PR #90 were unchanged.

### 2026-09-04 — owner-auth unexpected-status incident isolated and bounded

- public PR #155 exact head `9315fa90ba1c23bfaf8c4a51c281aea73fa6e1f2` passed Apex CI `33899930858` and Ops Contract `33899930818` and merged at `a533a9bcd25699f0f9fe444f11487ac271923471`;
- merged Draft relay `33901095469` failed before any Draft request because frozen Official FPL owner `/api/me/` verification returned an unexpected non-200/non-401/non-403 status;
- one bounded rerun reproduced the same failure and blind refresh retries stopped;
- historical non-serving direct-auth workflow run `33662138778` was rerun with current static bearer and refresh disabled; it independently reproduced the same frozen `/api/me/` unexpected-status class;
- PR #156 then added only failure-gated streamed status-code/class reporting, reading no body/headers, exposing no credentials and unable to recover auth or unlock Draft querying;
- refresh/auth recovery semantics, machine authority, AIrsenal serving, frozen PR #90, private owner surfaces and Draft no-write policy were unchanged by that diagnostic PR.

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
