# FPL Apex — Canonical Master State

> **MANDATORY CONTINUITY FILE — READ BEFORE ANY SUBSTANTIVE WORK**
>
> This is the canonical human/project continuity ledger for FPL Apex. It exists so a fresh ChatGPT, Codex, Claude, human maintainer or CI operator can recover the project without relying on conversation memory.
>
> It does **not** replace machine authority or immutable evidence. Where this prose conflicts with machine-verifiable state, the precedence rules below apply and this file must be corrected in the same change that discovers the conflict.

**Ledger schema:** 1  
**State snapshot:** 6 September 2026, after PR #172/evaluation-orphan repair and live owner-auth reconciliation; direct owner authentication is operational, durable refresh Keepalive remains degraded pending one external secret re-seed  
**Season:** 2026/27  
**Public control-plane repository:** `mcnuggets651/fpl-apex`  
**Private persistence/query repository:** `mcnuggets651/fpl`  
**Production Classic entry:** `63984`

---

## 0. Authority and precedence — never improvise this

When sources disagree, use this order:

1. **Immutable release evidence and current GitHub facts** — immutable release payloads/attestations/digests, current branch/PR/workflow state and live Official FPL facts.
2. **Machine production authority** — `docs/APEX_V2_AUTHORITY.json`.
3. **This master state ledger** — canonical human continuity/history/next-step record.
4. **Capability registry** — `docs/APEX_CAPABILITY_REGISTRY.yaml`; semantic index, not serving authority.
5. **Current system map/supporting Project Brain docs** — `docs/APEX_ARCHITECTURE.md`, `docs/CURRENT_STATE.md`, `docs/APEX_MASTER_CONTEXT.md`, `docs/APEX_OPERATING_MANUAL.md`, `docs/APEX_DECISIONS.md` and operational runbooks.
6. **Conversation/project memory** — context only; never authority for squad, prices, transfers, SHAs, release identity, model state, Draft roster/waivers or readiness.

If a fresh session cannot reconcile tiers 1–3, stop before making a manager recommendation or changing production and resolve the discrepancy from GitHub/release evidence.

### Mandatory startup read order

Before changing code, workflows, governance, model behavior, production operations, query behavior, documentation asserting current state or manager-facing decision logic:

1. read this file completely;
2. read `docs/APEX_V2_AUTHORITY.json`;
3. read `docs/CURRENT_STATE.md` and `docs/APEX_OPERATING_MANUAL.md`;
4. read `docs/APEX_CAPABILITY_REGISTRY.yaml` and `docs/APEX_ARCHITECTURE.md`;
5. read the runbook/contract/tests referenced by the registry for the capability being touched;
6. verify live GitHub `main`, relevant PRs, required checks/ruleset and immutable release/workflow state;
7. for owner-specific questions, use the private query boundary — never reconstruct manager or Draft state from chat memory.

`AGENTS.md` and `CLAUDE.md` encode this startup contract. CI enforces same-change master continuity and semantic capability/change-surface coverage.

---

## 1. Current executive status

# **APEX OPERATIONAL — DIRECT OWNER AUTH OPERATIONAL; DURABLE REFRESH DEGRADED**

The serving production chain and accepted Classic owner-private query architecture are operational. The current authentication condition is **not a global owner-API outage**: canonical Daily Production run `34011478768`, attempt 2, succeeded end-to-end on 6 September 2026, including authority verification, production-core ancestry, owner authentication/recovery, manager recovery, Official FPL sealing, provider acquisition, solve and immutable publication. Direct owner access is therefore currently usable by the governed production/Draft surfaces.

A separate durability condition remains degraded. Auth Keepalive run `34016839565`, attempt 2, failed closed because both the active rotating refresh credential and configured bootstrap refresh credential were rejected/expired. Keepalive correctly refused to pretend a direct bearer/cookie was a durable refresh-chain recovery. **Keepalive failure is not equivalent to direct-owner-auth failure.** Durable refresh health must remain a distinct gate.

The cached-access repair is already merged in PR #169 at `482ccacf5c995a3b6d256221fef9e2db69c34f7d`. It prevents the prior 15-minute Draft relay cadence from unnecessarily exchanging a one-time refresh parent on every successful authenticated poll. Valid manager-certified cached access is verified and reused; only an explicit Official-FPL `rejected` result permits refresh rotation. Wrong-manager, network or unclassified verification fails closed without consuming the refresh parent. The #157/#158 two-phase staged-child durability boundary remains intact.

The remaining durable-refresh repair is **external-secret state, not another code bypass**: obtain one fresh browser-issued `FPL_REFRESH_TOKEN`, enter it directly into the approved GitHub Actions secret, then run Keepalive once. Never paste the token into chat, repository content, logs or public artifacts. After that bootstrap succeeds, repeated authenticated runs must prove cached-access reuse without unnecessary refresh exchange before durable auth is called fully healthy.

The incident-only direct-auth diagnostic is being corrected so it uses the authority-selected `production_core_sha` for live owner preflight/config while retaining `frozen_engine_sha` only as an ancestry/forensic anchor. It remains manual-only, read-only, non-serving, refresh-disabled and incapable of rebuilding Keepalive state. This is an `OPS-002`/`GOV-002` control-plane correction only; it cannot change machine authority or serving output.

AIrsenal remains sole serving provider H1–H8. Dastan, Apex Proprietary and PITCHSIDE remain non-serving research/challenger surfaces unless formally promoted. Frozen PR #90 remains open/draft/unmerged and must never be merged or advanced.

### Historical auth incident context — superseded as current status

The 4–5 September incidents remain important forensic history but **must not be read as the current live status**. On 5 September run `33944494956` and later auth evidence showed then-current rotating/bootstrap refresh credentials rejected. Investigation found refresh amplification: Draft Relay ran at `7,22,37,52 * * * *` and the old private-refresh path exchanged refresh state on every authenticated invocation. Serialization under `apex-v2-fpl-auth` prevented simultaneous races but did not make that refresh frequency appropriate.

PR #156 classified the prior exhausted credential condition. PR #157 merged two-phase refresh durability at `1219861f3b9c3d707f6c80f94fa6f26325bab4a1`. A fresh browser re-seed then proved successful bootstrap exchange, private staged-child persistence and exact manager verification. PR #158 merged at `8efaa70b1172b0a0c6d20357d5d528a5a65ac8b7` to remove the same-run GitHub release-list visibility race. PR #169 then added manager-certified cached-access reuse to remove refresh amplification. Those code repairs remain accepted; the currently rejected refresh secrets simply require one fresh external re-seed for durable Keepalive health.

### Production acceptance

Historical canonical production acceptance remains run `33850307770-1`, which produced a matched immutable public/private GW3 release pair and proved the two-repository serving architecture.

- workflow run: `33850307770`;
- immutable run ID: `33850307770-1`;
- production core: `c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437`;
- frozen forensic base: `99cc7b51b0cff45462b567084cb1844cfe0a456f`;
- serving provider: AIrsenal H1–H8;
- authentication, Official FPL acquisition, AIrsenal generation, frozen solve, publication witness, public final and private manager publication: passed.

Fresh operational proof is Daily Production `34011478768`, attempt 2, which succeeded on 6 September 2026. Treat the immutable artifacts/current authority, not this prose, as the source for exact fresh manager values.

### Owner-private Classic query acceptance

The former GitHub-hosted billing blocker is closed without increasing spending limits. Private repo `mcnuggets651/fpl` uses the dedicated repository-level self-hosted runner `fpl-apex-private-mac` on the existing Mac with no `ubuntu-latest` fallback.

Required strategy acceptance modes historically passed:

- explicit exact run `33850307770-1`: strategy workflow `33868412431` — success;
- authority-selected `latest`: strategy workflow `33868662109` — success;
- private master-state contract `33868662187` — success.

Exact/latest narrow strategy JSON was byte-identical at SHA-256 `e50c4ebde19a2c68bfa4c38f33a6dd81f1d0922851f1e932bae522a898609d60`. Historical GW3 owner values remain historical only; current owner state must be queried from current governed evidence.

### Current provider-query closure

Private PR #8 repaired the chat-facing projection request that had remained pinned to historical run `33719526625-1`. It merged at `2f4ac141224f1fe222de6893a544abfbf685ea6a`; post-merge private contract/query runs succeeded and resolved authority-selected immutable evidence. Missing provider exports must remain explicit missing evidence rather than fabricated rows.

### FPL Draft owner-query closure

The Draft connection is historically runtime-proven and does not depend on chat memory. Private PR #9 merged live roster/available/locked query; private PR #10 added the credential-free authenticated-relay receiver; public PR #154 registered governed authenticated relay capability; private PR #12 established the stable private connected-session surface.

The stable receipt proved authenticated connectivity for live Draft team-entry ID `172178`, but result-bearing transaction rows are resolved history, not a certified current open queue. PR #155 hardened resolved/unresolved semantics and schema-only authenticated discovery. No Draft POST/DELETE/write capability was introduced.

Current Draft queries must continue to use live Official Draft evidence through the private boundary. A successful transaction-history endpoint with zero rows does not by itself prove no open waivers unless exact current-state semantics are established.

---

## 2. Current live repository/authority snapshot

These values are a dated continuity snapshot. Verify live GitHub at session start; never treat mutable `main` as permanent.

### Public repository

- repository: `mcnuggets651/fpl-apex`;
- PR #150 established canonical continuity;
- PR #151 established capability/documentation constitution;
- PR #152 closed the documentation loop;
- PR #153 repaired Dastan core-root execution;
- PR #154 completed governed Draft authenticated relay;
- PR #155 hardened Draft open-waiver semantics;
- PR #156 added bounded auth status diagnosis;
- PR #157 merged two-phase auth durability;
- PR #158 fixed same-run auth activation race;
- PR #160 closed PITCHSIDE predeadline reseal recovery;
- PR #161/D033 committed price-aware receding-horizon owner transfer planning as the required successor destination;
- PR #169 merged cached-access auth reuse at `482ccacf5c995a3b6d256221fef9e2db69c34f7d`;
- PR #172 merged the exact historical failed-attempt acknowledgement repair; main after that merge was `b9cfc0b63918442190eae0d984c9a847860337fe`;
- Daily Evaluation `34026370477` and downstream Decision Quality `34026458104` passed after #172;
- protected control plane: verify current ruleset live before relying on an old identifier.

### Machine authority

`docs/APEX_V2_AUTHORITY.json` is current machine authority and, at this snapshot, declares:

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
- Dastan role: `SHADOW`, serving unauthorized;
- PITCHSIDE role: `SHADOW`, serving unauthorized;
- research production influence: `NONE`;
- automatic promotion: `false`;
- legacy status: `HISTORICAL_NON_SERVING`.

Control-plane auth diagnostics and documentation reconciliation do not change machine authority.

### Frozen PR #90

PR #90, **Build Apex V2 clean-room production architecture**, remains deliberately open, draft, unmerged and not an operations branch. The immutable forensic anchor is `99cc7b51b0cff45462b567084cb1844cfe0a456f`. Policy remains **NEVER_MERGE_OR_ADVANCE**.

### Private repository

- repository: `mcnuggets651/fpl`;
- owner-private payloads, exact manager commitments, Draft owner transactions and authentication material remain private;
- accepted self-hosted/private query architecture remains the only approved current-owner query boundary;
- private Draft workflow does not receive reusable FPL credentials; public governed auth relays only credential-free allowlisted evidence.

---

## 3. Immutable GW3 production proof

Public final tag: `apex-v2/final/2026-2027/33850307770-1`.

- release ID: `382559137`;
- immutable: yes;
- published: `2026-09-04T07:51:49Z`;
- target commitish: `c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437`.

Public release digests remain immutable evidence. Matching private namespaces exist for private final/evaluation/presentation/tournament evidence. Exact private payloads/digests belong in the private companion, not this public ledger.

Architectural conclusion remains: `fpl-apex` is public control/authority/research-safe publication; `fpl` is owner-private persistence/query. Do not collapse the repositories or move private manager/Draft state public.

The successful GW3 serving run also isolated a non-serving Dastan core-root defect. PR #153 repaired repo-relative execution without changing AIrsenal serving authority. PITCHSIDE same-run predeadline recoverability was later closed by PR #160. Challenger runtime health never implies serving authorization.

---

## 4. Permanently closed production defects

PR #146, **Make production single-solve and publication witness-only**, permanently removed duplicate expensive optimisation during publication and corrected the one-candidate path. Production explicitly uses one primary max-xP candidate, records the true qualified planning horizon and does not rerun the optimiser during publication.

PR #147 promoted repaired production core `c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437` after required acceptance. This is closed engineering; do not reopen without new reproducible defect evidence.

---

## 5. Authentication recovery — current contract

The authenticated Classic/Draft surfaces share one governed auth lifecycle. There is not a second Draft credential owner.

Accepted security/durability sequence:

1. newest active encrypted private auth state is loaded;
2. if manager-certified cached access exists, verify it against Official FPL `/api/me/` for entry `63984`;
3. matching cached access is reused without exchanging refresh state;
4. only explicit access `rejected` permits refresh rotation;
5. wrong-manager, network or unclassified verification fails closed and preserves the refresh parent;
6. rotation uses the #157/#158 two-phase protocol: stage encrypted child privately before manager verification, verify exact manager identity, then activate exact staged release/digests;
7. indeterminate post-exchange state cannot fall through to another bootstrap/direct path;
8. wrong-manager staged state is purged/stopped;
9. same-run activation uses the exact staged release ID/digest map; cross-run recovery may list/re-download/decrypt staged state.

### Current live state

- direct owner auth: operational, evidenced by successful canonical Daily Production `34011478768-2`;
- durable refresh Keepalive: degraded, evidenced by failed Keepalive `34016839565-2` after both active rotating and bootstrap refresh credentials were rejected/expired;
- direct bearer/cookie must **not** be treated as durable Keepalive success;
- cached-access code is merged (#169); the remaining refresh-chain bootstrap is secret-side state;
- required external action: enter one fresh browser-issued `FPL_REFRESH_TOKEN` directly into the approved GitHub Actions secret, never chat/repository/logs;
- after rotation: run Keepalive once, then require repeated serialized cached-access successes with no refresh exchange before declaring durable auth healthy.

The incident-only direct-auth diagnostic may prove direct owner credential health only. It is manual-only, read-only, non-serving, refresh-disabled and must execute the auth preflight from the authority-selected `production_core_sha`; `frozen_engine_sha` is ancestry/forensic lineage only. It is not a Keepalive fallback and cannot activate, solve or publish.

---

## 6. Private query bridge contract

A chat session must answer owner questions without putting manager state in public GitHub and without reconstructing it from memory.

### Classic `latest`

`latest` means authority-linked current private manager evidence, not newest timestamp. The bridge filters by exact linked public attempt identity; publication time only breaks ties among authority-correct candidates. If no authority-correct candidate exists, fail closed.

### Classic integrity

Verify immutable private manager release, GitHub asset digests, Apex attestations, season/run identity, public-attempt linkage, entry `63984`, exact 15-player TeamState, bank/FT/prices/chips/transfers and narrow private-safe output. Private-auth releases are never query data.

### Draft query

For current Draft roster/market questions use current private Draft query evidence and require exact league/entry plus complete 15-player roster. For authenticated transaction evidence use the governed public relay + private receipt. Result-bearing rows are resolved history; missing/empty result rows are only `unresolved` until exact pending/open semantics are proven. Missing/auth-required/auth-rejected/endpoint-failed evidence is not an empty queue. Draft↔Classic projection joins use name + club + position, never raw numeric ID equality.

Detailed procedure: `docs/APEX_DRAFT_QUERY.md`.

---

## 7. Production constitution — closed decisions

### Factual authority

Official FPL is authoritative for player identity/element ID, club, FPL position, price/status/availability, fixtures/deadlines and exact manager mechanics when authenticated. Official FPL Draft is authority for configured Draft league roster/ownership/availability/transaction state.

### Serving forecasts

AIrsenal is current production champion and sole serving provider H1–H8. Shadow/challenger disagreement is diagnostic/research evidence only unless promoted through explicit governance.

### Manager-decision objective

Apex's owner-facing product is the legal squad-management decision. Forecasts are inputs. Receding-horizon transfer planning must compare ROLL against legal transfer paths from exact owner state and carry FT/bank/future optionality. D033 makes price-aware transfer planning a required production-core successor capability. Price uncertainty may alter affordability/continuation value only; it may not manufacture fantasy points or arbitrary team-value reward.

### Research isolation

- no silent fallback;
- no model voting into production;
- no arbitrary blend;
- no automatic challenger promotion;
- `research.production_influence = NONE`;
- no hindsight/backfilled prospective evidence.

### Solve mechanics

- one frozen snapshot per production attempt;
- no network during solve;
- exact FPL mechanics;
- provider-blind legal optimisation after forecast acquisition;
- max-EV primary policy;
- one canonical recommendation;
- immutable public/private persistence with run identity/provenance.

### Privacy

Public releases/docs/logs must not contain manager-private squad state, exact commitments, credentials, authenticated Draft owner transaction rows or unfiltered private provider material. Cached access and refresh tokens remain encrypted inside the private auth asset and are never public/query data. Owner-auth incident diagnostics may expose only bounded status/mode metadata, never credential values or response bodies.

### Frozen engine separation

`frozen_engine_sha` is immutable forensic lineage. `production_core_sha` is the independently promoted serving pointer and resolver for live production-core auth preflight/config. Never update or merge PR #90 to promote production or repair auth.

---

## 8. Repository architecture and important surfaces

### Documentation constitution

- `docs/APEX_V2_AUTHORITY.json` — machine serving authority;
- `docs/FPL_APEX_MASTER_STATE.md` — human continuity/evidence ledger;
- `docs/APEX_CAPABILITY_REGISTRY.yaml` — semantic capability/change-surface index;
- `docs/APEX_ARCHITECTURE.md` — current cross-repository V2 system map;
- `docs/APEX_DECISION_INDEX.yaml` — machine-readable decision status/supersession;
- `docs/APEX_DECISIONS.md` — append-only rationale/history;
- `docs/APEX_DRAFT_QUERY.md` — governed Draft owner-query/relay runbook.

Do not create a competing current architecture map, registry or master ledger.

### Public control plane

Important auth/Draft surfaces:

- `scripts/apex_v2_auth_ops.py` — serialized production auth controller with cached-access reuse and two-phase refresh durability;
- `.github/workflows/apex-v2-auth-keepalive.yml` — durable auth maintenance, authority-selected production-core boundary;
- `.github/workflows/apex-v2-direct-auth-diagnostic.yml` — incident-only direct-owner diagnostic; manual/read-only/non-serving/refresh-disabled;
- `.github/workflows/apex-v2-draft-auth-relay.yml` — authenticated read-only Draft relay;
- `scripts/apex_v2_draft_auth_relay_ops.py` — credential-stripping relay + bounded schema-only diagnostics;
- `docs/APEX_V2_DAILY_OPERATIONS.md` — auth/production runbook.

The Draft relay is not a serving workflow and cannot submit Draft transactions. Its 15-minute cadence must reuse valid cached access rather than imply 15-minute refresh rotation.

### Private persistence/query plane

Key surfaces include immutable Classic manager/provider persistence/query, encrypted auth releases/staged drafts, Draft query/relay ingestion, stable private receipt and the self-hosted runner. The private Draft workflow never receives reusable FPL credentials.

---

## 9. Compressed durable engineering lineage

GitHub remains the exact per-commit/per-PR archive. This section prevents settled work being rediscovered as blank-slate design.

- **Era A — V1 foundations/Project Brain (#1–#25):** AIrsenal horizons, Pinnacle/Elite robustness, readiness gates, baselines, replay/evidence/query policy, Project Brain.
- **Era B — sealed decisions/exact mechanics (#26–#44):** sealed bundles, exact FPL mechanics, authoritative evidence, no-hindsight replay, publication integrity and fail-closed behavior.
- **Era C — max-EV/transfer-aware planning (#45–#65):** max-EV-first policy, calibration experiments, multi-week transfer paths, role evidence, receding horizon and V1 freeze.
- **Era D — pre-clean-room V2 (#67–#89):** acquisition/projection/optimisation/persistence/governance exploration; historical/research only.
- **Era E — clean-room V2 constitution (#90–#96):** frozen PR #90 lineage, champion/challenger logic, proprietary shadow, daily operations and initial Draft availability.
- **Era F — auth/production operations (#97–#110):** authenticated owner recovery, Keepalive/diagnostics, deadline watching, decision quality and tournament hardening.
- **Era G — research/runtime engineering (#111–#114):** specialist learning and private Decision Quality lab.
- **Era H — authority reconciliation (#115–#123):** separation of immutable frozen SHA from movable promoted production-core SHA.
- **Era I — reproducibility/promotion/query foundations (#124–#137):** replay portability, deterministic promotion, auth recovery and private decision provenance.
- **Era J — production closure (#138–#149):** #146 single-solve witness-only repair, #147 production-core promotion, successful production run #9, Deadline Watch restoration.
- **Era K/L — continuity/private query constitution (#150–#152 + private work):** master ledger, capability registry, system map, zero-cost private self-hosted query path.
- **Era M — Draft/auth durability (#153–#158):** Dastan core-root repair, authenticated Draft relay, Draft semantics, auth diagnostics, two-phase refresh staging and same-run activation fix.
- **Era N — PITCHSIDE/D033/auth cache/evaluation repair (#160–#172):** PITCHSIDE reseal recovery, transfer-policy product commitment, cached-access auth reuse, proprietary shadow wiring work, exact historical failed-attempt acknowledgement and evaluation recovery.

Exact historical run/PR evidence remains preserved in repository history and immutable GitHub releases. Do not reinterpret compressed lineage as serving authority.

---

## 10. Known traps — future agents must not repeat these loops

1. Do not rebuild current Classic/Draft state from old chats/screenshots; query owner-private state.
2. Do not treat publication timestamp as Classic `latest`; public-attempt linkage comes first.
3. Do not merge or advance PR #90; promotion uses `production_core_sha`.
4. Do not rerun optimiser in publication; publication is witness verification.
5. Do not let shadow providers influence serving implicitly.
6. Do not backfill prospective evidence after outcomes.
7. Do not put private manager/Draft/auth material in public artifacts/docs/logs.
8. Do not create competing master/registry/system-map documents.
9. Do not leave state-changing code undocumented; CI requires master continuity.
10. Do not describe result-bearing Draft transaction rows as pending/open waivers.
11. Do not copy FPL credentials into the private Draft workflow.
12. Do not assume Draft and Classic element IDs are equal; reconcile name + club + position.
13. Do not submit a Draft write merely to manufacture semantic evidence.
14. Do not bind live owner auth to frozen forensic code when authority selects a promoted core.
15. Do not exchange a refresh parent before making the child durably recoverable.
16. Do not retry a consumed refresh parent when staged child evidence exists.
17. Do not fall through to bootstrap/direct auth after indeterminate post-exchange state.
18. Do not make same-run auth activation depend on eventual-consistency release listing.
19. Do not equate auth serialization with sensible refresh frequency.
20. Do not rotate refresh state because cached-access verification had network/unclassified failure; only explicit `rejected` permits rotation.
21. Do not treat a failed Keepalive refresh chain as proof direct bearer/cookie is unusable; direct auth and durable refresh are separate health dimensions.
22. Do not treat a successful direct-auth diagnostic as durable Keepalive recovery; the diagnostic has refresh disabled and no activation path.
23. Do not run live owner preflight/config from `frozen_engine_sha`; use authority-selected `production_core_sha`, retaining frozen SHA only for ancestry/forensics.
24. Do not synthesize/delete/rewrite a final release to make historical failed production intents disappear; the attempt audit may acknowledge only verified exact historical failures and must hard-fail on unknown future orphans.
25. Do not permanently park D033 price-aware transfer planning in research/shadow; canary is a certification gate, not final destination.

---

## 11. Next actions — durable refresh acceptance, then owner decision work

Current ordering:

1. merge the direct-auth diagnostic correction only after exact-head Apex CI/Ops Contract are green; it must remain manual/read-only/non-serving/refresh-disabled and use authority-selected `production_core_sha`;
2. **external secret-side action:** obtain one fresh browser-issued `FPL_REFRESH_TOKEN` and set only the approved GitHub Actions secret; never paste it into chat/repository/logs;
3. after secret rotation, run exactly one Keepalive verification and require successful durable bootstrap/activation;
4. require subsequent serialized owner-auth runs to reuse manager-certified cached access with no unnecessary refresh exchange;
5. only explicit cached-access rejection may cause the next single controlled rotation;
6. keep canonical Daily Production, Daily Evaluation and Decision Quality healthy; current Daily Evaluation `34026370477` and Decision Quality `34026458104` are green after #172;
7. use fresh immutable/private owner evidence for any exact TeamState/FT/bank/prices/transfer recommendation;
8. continue D033 price-aware receding-horizon successor implementation/promotion under deterministic replay, mechanics, privacy, price-scenario and canary gates;
9. keep PR #90 frozen and machine authority unchanged unless a separately governed promotion explicitly changes `production_core_sha`.

**Do not rerun Keepalive repeatedly while the known refresh credentials are rejected.** That does not repair the external secret and creates noise. Rotate the secret once, then run the bounded acceptance sequence.

---

## 12. Change-control protocol

Every substantive repository change must answer:

- What changed?
- Why?
- Which `Apex-Capabilities` does it affect?
- Which authority/invariant does it affect?
- What exact tests/CI/release evidence prove it?
- What did not change?
- What is the next action?
- Does a closed decision need reopening; if yes, what new evidence justifies it?

### Capability declaration rule

Public PRs declare:

- `Apex-Capabilities: <comma-separated registry IDs>`;
- `Apex-Authority-Changed: yes|no`;
- `Apex-Invariants-Changed: <description|none>`;
- `Apex-Decisions-Reopened: <IDs|none>`.

`scripts/check_capability_registry.py` compares declarations with registered change surfaces.

### Same-change rule

If any tracked public repository file changes, `docs/FPL_APEX_MASTER_STATE.md` must also change in the same PR/commit, except when the only changed tracked file is the master state itself. Private repo uses its companion rule.

Editing this ledger/registry/system map cannot promote serving authority, publish a production attempt or establish an owner decision. Those require existing machine/release/governance mechanisms.

---

## 13. Changelog for this ledger

### 2026-09-06 — direct auth/durable refresh status reconciled; diagnostic core selection corrected

- live canonical Daily Production `34011478768`, attempt 2, succeeded end-to-end, proving owner access is not globally fail-closed;
- Auth Keepalive `34016839565`, attempt 2, failed because active rotating and bootstrap refresh credentials were rejected/expired; this is durable refresh degradation, not proof that direct owner bearer/cookie is unusable;
- Keepalive semantics remain fail-closed and cannot substitute direct auth for a durable refresh chain;
- `.github/workflows/apex-v2-direct-auth-diagnostic.yml` is corrected to resolve `production_core_sha` from machine authority, verify frozen ancestry, materialize that exact core and run direct-only owner preflight there;
- the direct diagnostic remains `workflow_dispatch` only, `contents: read`, refresh-disabled, non-serving and without provider/intent/solve/publication paths;
- `frozen_engine_sha` remains the forensic ancestry anchor only; PR #90 remains untouched;
- machine authority, `production_core_sha`, AIrsenal serving H1–H8, research influence and private owner boundaries are unchanged;
- durable-refresh closure still requires one fresh browser-issued `FPL_REFRESH_TOKEN` entered directly into GitHub Actions secrets, followed by one Keepalive verification and cached-access reuse evidence.

### 2026-09-06 — evaluation orphan audit reconciled

- Daily Evaluation identified immutable failed production intents `33784086615-1` and `33809325241-1` without finals;
- both backing production attempts were verified as genuine failures and neither has a legitimate final;
- PR #172 added only those exact IDs to the historical-failure acknowledgement set; unknown future missing finals remain hard failures;
- PR #172 merged to `b9cfc0b63918442190eae0d984c9a847860337fe`;
- Daily Evaluation `34026370477` passed and downstream Decision Quality `34026458104` passed;
- no final was synthesized, deleted or rewritten; serving/model authority was unchanged.

### 2026-09-05 — cached-access auth repair

- refresh amplification was isolated: frequent Draft relay polls could exchange refresh state on every authenticated invocation despite serialized auth ownership;
- PR #169 merged manager-certified encrypted cached-access reuse at `482ccacf5c995a3b6d256221fef9e2db69c34f7d`;
- valid cached access is reverified/reused, explicit rejection permits rotation, wrong-manager/network/unclassified state fails closed and preserves the refresh parent;
- #157/#158 two-phase staged-child durability remains intact;
- no machine authority/serving/Draft-write/private-query/frozen-PR policy changed.

### 2026-09-05 — owner transfer policy committed as production destination

- D033 records that Apex's primary owner-facing product is the legal transfer/squad-management decision;
- price-aware receding-horizon transfer planning is a required production-core successor destination;
- price movement may alter route feasibility/continuation value but may not create arbitrary team-value/xP reward;
- research/shadow/canary is transitional certification evidence, not a permanent terminal state.

### 2026-09-05 — PITCHSIDE recoverability and proprietary shadow operations

- PR #160 merged predeadline same-run content-addressed PITCHSIDE reseal recovery while preserving no-hindsight and research-only boundaries;
- proprietary shadow export wiring work remained non-serving and could not change AIrsenal serving authorization merely by producing a shadow export.

### 2026-09-04 — auth durability and Draft query closure

- PR #154 completed governed authenticated Draft relay;
- private PR #12 established the stable connected-session Draft receipt;
- PR #155 hardened resolved/unresolved/open-waiver semantics;
- PR #156 classified exhausted owner credentials without leaking auth material;
- PR #157 merged two-phase refresh durability;
- fresh browser re-seed proved bootstrap exchange, private child staging and exact manager verification;
- PR #158 removed the same-run release-list activation race;
- no Draft write capability was introduced.

### 2026-09-04 — production/query/documentation closure

- canonical production run `33850307770-1` proved the serving architecture;
- private exact strategy `33868412431` and authority-selected `latest` strategy `33868662109` succeeded with byte-identical narrow output;
- PR #150 introduced canonical master continuity;
- PR #151 introduced the capability/documentation constitution;
- PR #152 closed the documentation loop;
- PR #153 repaired Dastan core-root orchestration without serving impact.

### Historical lineage note

Earlier V1/V2 PR-by-PR details, exact run IDs, release assets and acceptance evidence remain permanently available in Git history and immutable release evidence. This ledger intentionally keeps the current state and closed architectural decisions readable while preserving the exact repository/release archive as higher-precedence forensic evidence.
