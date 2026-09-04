# FPL Apex — Canonical Master State

> **MANDATORY CONTINUITY FILE — READ BEFORE ANY SUBSTANTIVE WORK**
>
> This is the canonical **human/project continuity ledger** for FPL Apex. It exists so a fresh ChatGPT, Codex, Claude, human maintainer, or CI operator can recover the project without relying on conversation memory.
>
> It does **not** replace machine authority or immutable evidence. Where this prose conflicts with machine-verifiable state, the precedence rules below apply and this file must be corrected in the same change that discovers the conflict.

**Ledger schema:** 1  
**State snapshot:** 4 September 2026, after private current-provider query closure and during bounded Dastan core-root repair  
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
6. **Conversation/project memory** — useful context only; never authority for squad, prices, transfers, SHAs, release identity, model state or production readiness.

If a fresh session cannot reconcile tiers 1–3, it must stop before making a manager recommendation or changing production and resolve the discrepancy from GitHub/release evidence.

### Mandatory startup read order

Before changing code, workflows, governance, model behavior, production operations, query behavior, documentation that asserts current state, or manager-facing decision logic:

1. read this file completely;
2. read `docs/APEX_V2_AUTHORITY.json`;
3. read `docs/CURRENT_STATE.md` and `docs/APEX_OPERATING_MANUAL.md`;
4. read `docs/APEX_CAPABILITY_REGISTRY.yaml` and `docs/APEX_ARCHITECTURE.md`;
5. read the specific runbook/contract/tests referenced by the registry for the capability being touched;
6. verify live GitHub `main`, relevant PRs, required checks/ruleset and immutable release/workflow state;
7. for owner-specific questions, use the private query boundary — never reconstruct manager state from chat memory.

`AGENTS.md` and `CLAUDE.md` encode this startup contract for automated agents. CI enforces both same-change master continuity and semantic capability/change-surface coverage.

---

## 1. Current executive status

# **APEX OPERATIONAL**

The serving production chain and owner-private query chain have both completed their required acceptance.

A bounded non-serving challenger repair is currently in progress: canonical production run `33850307770-1` proved AIrsenal serving and the owner decision path, but its Dastan H1 shadow acquisition failed with a control-plane/core working-directory defect. PITCHSIDE and Dastan remain research-only and this defect does **not** change the operational serving status or authority.

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

### Owner-private query acceptance

The former GitHub-hosted billing blocker has been eliminated without increasing spending limits. Private repo `mcnuggets651/fpl` now uses a dedicated repository-level self-hosted runner on the existing Mac:

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

Both resolved:

- immutable run `33850307770-1`;
- entry `63984`;
- exactly 15 unique owned players;
- bank £0.5m;
- 1 free transfer;
- no active chip;
- complete purchase/selling prices;
- complete transfer state;
- narrow private-safe output only.

The final `latest` run re-read public authority and selected the authority-correct private manager release, not merely the newest publication. Historical zero-step billing failures remain provenance only and are not current blockers.

### Current provider-query closure

Private PR #8 repaired the chat-facing projection request that was still explicitly pinned to historical run `33719526625-1` after the accepted strategy path had moved to authority-selected `latest`.

- PR #8 exact head: `95d62c985acb838c5df9b830ad0051036c114783`;
- exact-head private master-state contract `33880335918`: success;
- merge commit: `2f4ac141224f1fe222de6893a544abfbf685ea6a`;
- post-merge private master-state contract `33880420453`: success;
- post-merge projection query `33880420585`: success;
- projection artifact ID `9939639578`, digest `sha256:c611bff6edbf49d8fbeeb92ea84e75c58d3404d37c86c6f84fc06393de847754`.

That query resolved exact current immutable run `33850307770-1`, the matching private evaluation namespace and the matching private PITCHSIDE tournament namespace. It exposed current PITCHSIDE rows for the requested strategy universe. The same-run provider archive contained AIrsenal only because Dastan had failed earlier during production acquisition; the private query bridge itself was no longer the Dastan blocker.

### Operational qualification

`APEX OPERATIONAL` means a fresh connected agent can reproducibly recover and verify the authority-correct immutable owner state without relying on remembered squad information.

It does **not** mean a historical immutable decision is automatically fresh forever. Normal production freshness, deadline, authentication, Official FPL and provider-qualification gates continue to determine whether a new manager-facing recommendation is actionable.

It also does not mean every non-serving challenger must be healthy. A shadow failure is visible diagnostic evidence and may not change AIrsenal serving authority.

---

## 2. Current live repository/authority snapshot

These values are a dated continuity snapshot. At session start verify live GitHub; never treat a mutable `main` SHA as permanent.

### Public repository

- repository: `mcnuggets651/fpl-apex`;
- public continuity PR #150 merged successfully on 4 September 2026 at `a00f0a45d8e74d834f79cbc473a6482656b9feda`;
- PR #150 exact-head Apex CI `33870084591`: success;
- PR #150 exact-head Apex V2 Ops Contract `33870084665`: success;
- post-merge Apex CI `33870475132`: success;
- capability/documentation constitution PR #151 merged successfully on 4 September 2026;
- PR #151 exact head: `400210e12e829fab2d0ab4f85ee7f31aef96dea0`;
- PR #151 exact-head Apex CI `33873835393`: success;
- PR #151 exact-head Apex V2 Ops Contract `33873835399`: success;
- PR #151 merged at `6a1509f766e6438a43d296e8e900518a18967959`;
- post-merge Apex CI `33874537255`: success;
- PR #152 closed the final documentation-only loop and merged at `620ad5d305008c018c9ea3ccd887c9de8b510b9c` after exact-head Apex CI `33877989903` and Apex V2 Ops Contract `33877990068` passed;
- bounded branch `agent/fix-dastan-core-root` was created from exact `620ad5d305008c018c9ea3ccd887c9de8b510b9c` to repair the newly verified non-serving Dastan orchestration defect;
- protected control plane; historical ruleset identifier `21759706` — verify live before relying on it.

### Machine authority

`docs/APEX_V2_AUTHORITY.json` was re-read before the Dastan repair and remains unchanged:

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

The bounded Dastan repair does not change machine authority.

### Frozen PR #90

PR #90, **Build Apex V2 clean-room production architecture**, remains deliberately:

- open;
- draft;
- unmerged;
- not an operations branch;
- not a branch to advance as part of successor promotion.

The immutable authority anchor is forensic SHA `99cc7b51b0cff45462b567084cb1844cfe0a456f`. The policy remains **NEVER_MERGE_OR_ADVANCE**.

### Private repository

- repository: `mcnuggets651/fpl`;
- accepted final-latest merge commit: `a310450fd27aa469eac9ae91971334925b4bee77`;
- private operational-ledger closure commit: `9e55ee8e98fb15eeb0a5189c7e65b88c5a6467af`;
- private capability/documentation binding PR #7 merged at `459427fe1e90565d61f8a9f6547f3876c4f3ec9a`;
- PR #7 final exact-head private contract `33876581770`: success on `fpl-apex-private-mac`;
- PR #7 post-merge private master-state contract `33876640309`: success;
- current-provider query PR #8 merged at `2f4ac141224f1fe222de6893a544abfbf685ea6a`;
- PR #8 exact-head contract `33880335918`, post-merge contract `33880420453`, and post-merge Projection Query `33880420585`: success;
- private CI consumes and validates the single public `PRIV-001`–`PRIV-008` capability semantics and rejects a competing private registry;
- strategy request remains schema 1, `run_id="latest"`, `top_n=12`;
- projection request now uses `run_id="latest"`, exact current-strategy player IDs and `canonical/providers/pitchside` H1–H8 surfaces where available;
- owner-private payloads, exact manager commitments and authentication material remain private.

---

## 3. Successful immutable GW3 production proof

### Public final

Tag:

`apex-v2/final/2026-2027/33850307770-1`

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

Do not collapse the repositories or move private manager state into the public repo to simplify querying.

### Dastan incident evidence from run #9

The sanitized diagnostic artifact `apex-v2-diagnostic-33850307770-1` (artifact ID `9928201488`, digest `sha256:60d31b43aa5402e59df5376a6beb43553cdb903a12f581f0c520a2018a82b256`) proved that the optional Dastan step did not succeed even though the overall serving job did.

Its Dastan report recorded:

- provider `dastan`, pinned upstream `qazybekb/smartplayfpl-dastan@19376523afdec4836d0e6b5632c6773d0fe40c53`;
- `health = ERROR`;
- `state = ACQUISITION_FAILED`;
- `failure_class = PROVIDER_LOGIC_OR_INVARIANT_FAILURE`;
- one attempt, return code 1, non-transient;
- sanitized failure ending in `KeyError: 'dastan'`;
- `serve_authorized = false` and `production_influence = NONE`.

Root cause is orchestration, not Dastan model authority: `scripts/acquire_dastan_shadow.py` in the authority-selected production core defaults `--repo-root` to the current working directory and reads `<repo-root>/upstreams.lock.json`. The production workflow invoked that frozen runner while its current directory was the mutable control-plane checkout. The control-plane root lock intentionally does not contain `dastan`; the authority-selected production core lock does. The wrapper itself received the correct core lock for its retry metadata, which is why the failure could be diagnosed precisely.

The bounded repair changes only the Dastan orchestration step so it:

1. re-verifies `$APEX_CORE_PATH` is exactly `$APEX_CODE_SHA`;
2. removes any stale workspace Dastan surface;
3. invokes the existing operations wrapper from inside the authority-selected production-core worktree, causing the frozen Dastan runner's default repo root to resolve correctly;
4. writes the sanitized Dastan diagnostic back to the control-plane workspace;
5. requires a non-empty qualified core `acquisition/providers/dastan.csv` before copying it into the production acquisition workspace;
6. preserves `continue-on-error`, H1-only shadow status, no serving fallback, no blending and no authority change.

A regression contract in `ops_tests/test_apex_v2_shadow_provider_workflow.py` requires those exact boundaries. Runtime acceptance is still required after exact-head CI/ops checks and governed merge; until then do not claim Dastan has been restored.

---

## 4. Production defect that was permanently closed

### Defect A — duplicate optimisation during publication

The old production path performed the expensive H1–H8 candidate MIP search in the primary solve and reran it during publication. Repeated approximately 120-second MIPs expanded runtime to roughly 68 minutes and allowed time-bound solver-search details to differ, causing false nondeterminism.

### Defect B — incorrect one-candidate semantics

Even with one candidate requested, the optimiser ran primary, secondary and excluded-path MIPs and returned the secondary result while describing the primary as retained. Multi-week transfer decisions were also recorded with `horizon=1`, causing valid multi-week transfer paths to fail certification.

### Permanent repair — PR #146

PR #146, **Make production single-solve and publication witness-only**, implemented the bounded permanent fix and was merged into the promoted production core.

Production now:

- explicitly uses `candidate_limit=1`;
- executes exactly one primary MIP in the one-candidate path;
- retains the actual primary max-xP solution;
- records the true qualified planning horizon for multi-week decisions;
- never reruns the optimiser during publication;
- uses a deterministic frozen publication witness to verify snapshot/run/provider identity, canonical projection hash, exact mechanics, H1 lineup/captain/vice/bench/objective, reconstructed certification, deadline safety and provider freshness before release writes;
- retains multi-candidate research only when explicitly requested outside production.

Verification attached to this repair included:

- 42 relevant local tests passed;
- production single-candidate test proved exactly one `milp` invocation;
- all six critical semantic mutation sentinels were killed;
- lint passed;
- exact-head Apex CI `33846244269`: success;
- exact-head Apex V2 CI `33846244193`: success.

### Authority promotion — PR #147

PR #147 promoted repaired exact core:

`c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437`

Promotion checks:

- Apex V2 Ops Contract `33847263015`: success;
- Apex CI/readiness `33847263087`: success.

This is closed production engineering. **Do not reopen it without new reproducible defect evidence.**

---

## 5. Authentication recovery — closed unless evidence changes

Before production run #8, stored FPL tokens expired. Auth keepalive #22 failed and both rotating private refresh state and bootstrap refresh secret were rejected.

A fresh authenticated FPL browser session renewed the encrypted Actions secret. The credential was immediately exchanged/rotated and persisted through the private rotating state.

Acceptance run:

- auth keepalive `33850189866`: success;
- private-store preflight: passed;
- credential rotation: passed;
- new rotating state: persisted;
- frozen worktree integrity: passed.

The temporary browser refresh credential was rotated before production and is not the active credential. Never write credentials, token values or authenticated payloads into this file.

---

## 6. Private query bridge contract and completed acceptance

### Why the bridge exists

A chat session must be able to answer questions such as “what is my current FPL team?” or “should I transfer or roll?” without putting manager state in public GitHub and without reconstructing it from memory.

The private repository is the only approved owner-state/query surface.

### `latest` semantics

`latest` does **not** mean newest publication timestamp. The bridge first reads current public production authority and filters candidate private manager releases by exact linked `public_attempt_id`. Publication time can only break ties among authority-correct candidates. If no candidate matches, it fails closed with `REFRESH_REQUIRED`.

Explicit historical `run_id` requests directly resolve that immutable attempt, subject to integrity checks.

### Integrity contract

The accepted bridge verifies:

1. immutable private manager release;
2. GitHub release-asset digests before parsing;
3. Apex private attestations;
4. tag-derived and payload season/run identity;
5. attestation/payload `public_attempt_id` linkage;
6. entry ID `63984`;
7. exact 15-player unique TeamState;
8. bank, FT, purchase/selling prices, chip/status and transfer completeness;
9. no `private-auth` read;
10. narrow output without credentials, commitment keys or unfiltered private payloads.

### Zero-cost runner acceptance

Private continuity PR #4 established the dedicated self-hosted path. Important evidence:

- pre-registration self-hosted diagnostic `33860400423` queued with matching labels but no runner, proving separate repo registration was required;
- registered runner `fpl-apex-private-mac` on machine `BC02336`;
- corrected PR #4 exact-head contract `33867686466`: success;
- PR #4 merge commit `08f0979e97b67b0978f2abd35f726be48e832505`;
- post-merge private Projection Query `33867975154`: success;
- Manager Shape `33867975165`: success;
- Strategy Query `33867975181`: success;
- Master State Contract `33867975208`: success.

### Exact-run acceptance — PASSED

Private PR #5:

- head `ad7e1305173853831b07d328ac8e0ec0af36a4f2`;
- PR contract `33868373995`: success;
- merge commit `1ac3048383d3395d2ad7b0cbd566aa92329e4518`;
- explicit strategy run `33868412431`: success;
- artifact `apex-private-strategy-33868412431`;
- artifact ID `9934875378`;
- artifact digest `sha256:7b032b9738cee7e01d9fe06f40d0a135bfa84b53201e50d54c66022e869dffe5`;
- post-merge private contract `33868412440`: success.

The exact output resolved immutable run `33850307770-1`, entry `63984`, exactly 15 unique squad IDs, £0.5m bank, 1 FT, no active chip and complete purchase/selling-price transfer state.

### Final restored `latest` acceptance — PASSED

Private PR #6:

- head `4da60fc76d9751f25c7de37f0d074ddb17814527`;
- PR contract `33868620244`: success;
- merge commit `a310450fd27aa469eac9ae91971334925b4bee77`;
- final `latest` strategy run `33868662109`: success;
- artifact `apex-private-strategy-33868662109`;
- artifact ID `9934972157`;
- artifact digest `sha256:ec70331515fa3fff6dee9fb512c0cfc2001af98124cb9ab08fb3f0b64b0fe778`;
- post-merge private contract `33868662187`: success.

The final `latest` output independently selected authority-correct immutable run `33850307770-1` and had the same narrow state as exact mode.

Both exact and final `latest` JSON bytes share SHA-256:

`e50c4ebde19a2c68bfa4c38f33a6dd81f1d0922851f1e932bae522a898609d60`

This strategy-query acceptance gate is **closed**. The separate projection-request freshness defect was fixed by private PR #8 and did not invalidate owner-state acceptance.

---

## 7. Production constitution — closed decisions

These are constraints unless a separately evidenced governance change deliberately supersedes them.

### Factual authority

Official FPL is authoritative for:

- player identity and element ID;
- club;
- FPL position;
- current FPL price/status/availability;
- fixtures/deadlines;
- exact manager-state mechanics when authenticated.

### Serving forecasts

AIrsenal is current production champion and sole serving provider H1–H8. Shadow/challenger disagreement is diagnostic/research evidence only unless promoted through explicit governance.

### Research isolation

- no silent fallback;
- no model voting into production;
- no arbitrary blend;
- no automatic challenger promotion;
- `research.production_influence = NONE`;
- prospective evaluation must not backdate evidence;
- outcomes cannot be used to recreate allegedly predeadline decisions.

### Solve mechanics

- one frozen snapshot per production attempt;
- no network access during solve;
- exact FPL mechanics;
- provider-blind legal optimisation after forecast acquisition;
- max-EV primary policy;
- one canonical recommendation;
- immutable public/private persistence with run identity/provenance.

### Privacy

Public releases must not contain manager-private squad state, exact commitments, credentials or unfiltered private provider material. Private-auth releases are never query data.

### Frozen engine separation

`frozen_engine_sha` is immutable forensic lineage. `production_core_sha` is the independently promoted serving pointer. Never update or merge PR #90 to promote production.

---

## 8. Repository architecture and important surfaces

### Documentation constitution

Canonical public documentation surfaces now have separated responsibilities:

- `docs/APEX_V2_AUTHORITY.json` — machine serving authority;
- `docs/FPL_APEX_MASTER_STATE.md` — human continuity/evidence ledger;
- `docs/APEX_CAPABILITY_REGISTRY.yaml` — semantic capability/change-surface index, not serving authority;
- `docs/APEX_ARCHITECTURE.md` — single current cross-repository V2 system map;
- `docs/APEX_DECISION_INDEX.yaml` — machine-readable decision status/supersession;
- `docs/APEX_DECISIONS.md` — append-only rationale/history.

`docs/ARCHITECTURE.md` and `docs/APEX_CANONICAL_DECISION_POLICY.md` are explicitly historical/non-serving. Do not create a second current architecture map, second semantic registry or separate prose runbook index.

### Public control plane (`fpl-apex`)

Primary live surfaces:

- `docs/APEX_V2_AUTHORITY.json` — machine serving authority;
- `.github/workflows/apex-v2-daily-production.yml` — only serving production workflow;
- `.github/workflows/apex-v2-auth-keepalive.yml` — auth continuity only;
- `.github/workflows/apex-v2-deadline-watch.yml` — bounded production dispatch near deadline;
- `.github/workflows/apex-v2-daily-evaluation.yml` — prospective evaluation;
- `.github/workflows/apex-v2-prospective-tournament.yml` — non-serving champion/challenger evidence;
- `.github/workflows/apex-v2-decision-quality.yml` — non-serving decision-edge research;
- `.github/workflows/apex.yml` — required Apex CI/control-plane contract/readiness;
- `.github/workflows/apex-v2-ops-contract.yml` — operations/governance contract;
- `scripts/check_capability_registry.py` — semantic capability/change-surface enforcement;
- `ops_tests/` — mutable control-plane/operations regressions;
- `scripts/` — public control-plane checkers/orchestration;
- `archive/workflows/` — forensic history; operations contract rejects modification/resurrection.

Serving implementation is materialized from the exact authority-declared production core. `src/apex` is V2 lineage; legacy `src/apex_fpl`/old publishers are historical/non-serving and may not silently re-enter production.

Capability path validation is ref-aware: serving-core entry points are checked against `production_core_sha`; forensic evaluator entry points are checked against `frozen_engine_sha`; mutable `main` alone is not used to decide whether a live capability exists.

### Private persistence/query plane (`fpl`)

Key surfaces:

- `FPL_APEX_PRIVATE_MASTER_STATE.md` — canonical private continuity companion;
- `APEX_PRIVATE_QUERY_BRIDGE.md` — private projection query contract;
- `apex-query/request.json` — narrow player/projection query request;
- `apex-query/strategy_request.json` — owner multi-week strategy request, normally `latest`;
- `tools/apex_private_query_entry.py` — projection bridge entry;
- `tools/apex_strategy_query.py` — manager/multi-week strategy query;
- `.github/workflows/apex-private-query.yml` — narrow private projection query;
- `.github/workflows/apex-strategy-query.yml` — private strategy snapshot query;
- `.github/workflows/apex-master-state-contract.yml` — private continuity contract;
- `fpl-apex-private-mac` — dedicated repository-level self-hosted execution surface;
- private immutable releases — owner state/evaluation/presentation/auth separation.

Public registry `PRIV-*` capabilities document these boundaries semantically. Private PR #7 completed live private-path validation against the single public registry and added fail-closed enforcement for missing/wrong private bindings, a second private registry, stale acceptance state or hosted-runner fallback. There is no second private semantic registry.

---

## 9. Project history — compressed but durable engineering lineage

GitHub remains the exact per-commit/per-PR archive. This section records decision lineage so future sessions do not rediscover settled problems.

### Era A — V1 foundations and Project Brain (#1–#25)

Early work repaired AIrsenal horizons/refresh, Pinnacle/Elite robustness, production-readiness gates, canonical baselines, diagnostics, replay foundations, evidence semantics and answer/query policy.

**PR #7** created Project Brain v1.0 and established the first mandatory read-before-work protocol. The current master-state layer is an evolution of that design, not a replacement that discards history.

### Era B — sealed decisions, exact mechanics and evidence correctness (#26–#44)

This era introduced sealed decision bundles, retired duplicate publication paths, hardened missing-evidence behavior, exact FPL mechanics, authoritative evidence ingestion, no-hindsight replay, publication integrity, fail-closed behavior, core-refresh controls and AIrsenal horizon/fixture handling.

### Era C — max-EV, projection semantics and transfer-aware planning (#45–#65)

Key decisions included max-EV-first selection, projection truth/calibration experiments, explicit retirement of failed shrinkage variants, transfer-aware multi-week paths, Understat research, role evidence, zero-minute semantics, GW1-first/receding-horizon planning and a V1 architecture freeze.

**PR #66** is retained as large V1 archaeology/implementation history; it is not current serving authority.

### Era D — pre-clean-room V2 exploration (#67–#89)

A sequence of V2 slice/modernisation PRs explored acquisition, projections, optimisation, persistence, governance and operations. These are historical/research lineage, not current serving authority.

### Era E — clean-room V2 freeze and champion/challenger constitution (#90–#96)

- **#90** established clean-room production architecture and remains the permanent frozen lineage anchor; draft/open/unmerged.
- **#91** integrated champion–challenger prospective tournament logic into the frozen V2 line.
- **#92** added Apex proprietary shadow challenger behavior.
- **#94** activated frozen V2 daily operations on `main`.
- **#95–#96** added FPL Draft support without changing Classic serving authority.

### Era F — authentication and production operations (#97–#110)

This work recovered authenticated owner state, added keepalive/direct diagnostics, safe deadline watching, owner brief/decision-quality operations, a football-intelligence export bridge, shadow-provider reliability and prospective-tournament operational hardening.

### Era G — decision-edge research and runtime engineering (#111–#114)

Sequential specialist learning and the private Decision Quality lab were added. Heavy independent tasks became parallel/resumable and the per-task runtime contract was corrected to 50 minutes while preserving serving semantics.

### Era H — authority reconciliation and serving-core separation (#115–#123)

Repository documentation/operations were reconciled to V2 authority, Node-24/action pinning and archive controls were hardened, and adversarial successor certification was introduced.

**#122** made the crucial distinction between immutable `frozen_engine_sha` and movable `production_core_sha`. **#123** performed the first hardened successor promotion through the production-core pointer without touching the frozen PR.

### Era I — reproducibility, deterministic promotion and owner-query foundations (#124–#137)

Replay portability, reproducibility investigations, canaries, deterministic successor promotion, snapshot-clock repair, auth draft recovery, explicit `production_core_sha` authority, private decision-lab provenance and integration validation were hardened.

### Era J — final production closure and single-solve repair (#138–#149)

Temporary one-shot production dispatches were deliberately added/removed around controlled runs. Snapshot/core mismatch diagnostics isolated production issues. **#146** permanently eliminated duplicate production optimisation and made publication witness-only. **#147** promoted exact core `c0ae9f6e…`. Production run #9 succeeded. **#149** restored normal Deadline Watch and removed temporary dispatch hygiene.

### Era K — continuity and private-query operational closure (#150 public; private #4–#8)

- Public PR #150 established the canonical human continuity ledger, agent startup contracts and same-change CI enforcement and merged successfully at `a00f0a45d8e74d834f79cbc473a6482656b9feda`.
- Post-merge Apex CI `33870475132` completed successfully.
- Private PR #4 created the private continuity companion, migrated private workflows to zero-cost self-hosted execution, and proved the dedicated runner.
- Private PR #5 executed/accepted exact immutable-run strategy querying.
- Private PR #6 restored and accepted authority-selected `latest` strategy querying.
- Private PR #7 completed public-registry semantic binding in private CI.
- Private PR #8 repaired the stale projection request and proved authority-current PITCHSIDE access without altering serving authority.

### Era L — capability/documentation constitution and private binding closure

Public PR #151 completed the bounded documentation/governance constitution:

- added `docs/APEX_CAPABILITY_REGISTRY.yaml` as the one semantic index across governance/production/operations/research/private/interaction/legacy capabilities;
- added `docs/APEX_DECISION_INDEX.yaml` as machine-readable decision status/supersession while preserving `APEX_DECISIONS.md` rationale;
- repurposed `docs/APEX_ARCHITECTURE.md` as the single current V2 cross-repository system map;
- explicitly classified `docs/ARCHITECTURE.md` and `docs/APEX_CANONICAL_DECISION_POLICY.md` as historical/non-serving;
- added `scripts/check_capability_registry.py` plus adversarial `ops_tests/test_capability_registry_contract.py`;
- added semantic PR metadata and changed-path ↔ capability enforcement;
- wired the checker into existing Apex CI and Apex V2 Ops Contract, not a new workflow;
- passed exact-head Apex CI `33873835393` and Apex V2 Ops Contract `33873835399`;
- merged at `6a1509f766e6438a43d296e8e900518a18967959`;
- passed post-merge Apex CI `33874537255`.

Private PR #7 then completed the intentionally separate private semantic-binding closure:

- consumed the single public `APEX_CAPABILITY_REGISTRY.yaml` rather than creating a second registry;
- validated public `PRIV-001`–`PRIV-008` semantics against private workflows/tools/runbooks/tests;
- enforced the exact self-hosted `[self-hosted, macOS, ARM64]` / no-hosted-fallback boundary;
- corrected stale private acceptance language;
- passed final exact-head private contract `33876581770` on `fpl-apex-private-mac`;
- merged at `459427fe1e90565d61f8a9f6547f3876c4f3ec9a`;
- passed post-merge private contract `33876640309`.

Decision D032 records the public constitution. This sequence is closed documentation/governance work, not an invitation to restart model development or architecture redesign.

---

## 10. Known traps — future agents must not repeat these loops

1. **Do not rebuild the current squad from old chats/screenshots.** Query owner-private state.
2. **Do not treat publication timestamp as `latest` authority.** Exact public-attempt linkage comes first.
3. **Do not merge or advance PR #90.** Production promotion uses `production_core_sha`.
4. **Do not rerun the optimiser in publication.** Publication is deterministic witness verification.
5. **Do not restore multi-candidate search to production by changing reusable research defaults.** Production explicitly selects one candidate.
6. **Do not interpret historical zero-step GitHub Actions billing rejections as query-code failures.** Those are closed provenance.
7. **Do not switch private workflows back to billable hosted runners.** `fpl-apex-private-mac` is the intended zero-cost private execution surface.
8. **Do not weaken deterministic replay/certification to make a failing run pass.** Diagnose provenance/mechanics instead.
9. **Do not let shadow providers influence serving output implicitly.** They are prospective evidence only.
10. **Do not backfill prospective evidence after outcomes.** No hindsight.
11. **Do not resurrect archived legacy publishers.** Archive is forensic only.
12. **Do not put private manager payloads or credentials into public docs/releases/logs.**
13. **Do not create another competing master document.** Update this ledger and machine authority/supporting docs as appropriate.
14. **Do not create a competing capability registry, current system map or prose runbook index.** Use the registry and `APEX_ARCHITECTURE.md`.
15. **Do not copy movable serving/current state into the capability registry or architecture map.** Reference authority instead.
16. **Do not leave state-changing code undocumented.** CI requires this ledger to move with substantive changes.
17. **Do not create an active workflow or `scripts/apex_v2_*.py` surface without registering its capability.**
18. **Do not reopen exact/latest strategy-query acceptance without a new reproducible defect or authority change.**
19. **Do not reopen the public/private capability-binding closure merely because subordinate prose still contains historical future-tense wording.** This ledger and verified live GitHub state outrank that prose.
20. **Do not launch production-core helper scripts from the mutable control-plane working directory when those helpers resolve repo-relative locks/config/scripts.** Execute them against the authority-selected production-core root and explicitly materialize only their validated output into the production workspace.

---

## 11. Next actions — bounded Dastan runtime closure, then normal operations

The production/query system remains accepted. The only current engineering closure is the newly reproduced Dastan orchestration defect; it must not expand into a model redesign or serving-authority change.

For the bounded Dastan repair:

1. exact-head Apex CI and Apex V2 Ops Contract must pass on the repair PR;
2. merge only with an exact-head check and no authority/registry drift;
3. run the canonical production workflow from the merged control plane while the GW3 predeadline window is still valid, so the repair is tested on the same real production boundary rather than by hindsight reconstruction;
4. require the new sanitized Dastan diagnostic to show a healthy H1 acquisition and require the matching private evaluation archive to contain Dastan rows before calling the repair complete;
5. re-run the narrow private authority-selected projection query and verify same-run AIrsenal/Dastan plus matching PITCHSIDE surfaces;
6. use those coherent current surfaces only as diagnostic challenges around the AIrsenal-serving multi-week owner strategy.

Normal operations then remain:

1. keep `fpl-apex-private-mac` service healthy for private query execution;
2. keep public Deadline Watch/auth keepalive/production workflows healthy;
3. at each new deadline, obtain fresh Official FPL/auth/provider state through the production chain before making an actionable recommendation;
4. use private `latest` query for owner-specific retrieval and fail closed if it returns `REFRESH_REQUIRED`;
5. continue prospective research/evaluation without serving influence unless explicitly promoted through governance;
6. keep PR #90 frozen/open/draft/unmerged and never use its moving branch head as the immutable authority anchor;
7. update this ledger whenever substantive public state changes and the private companion whenever private state changes.

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

This is intentionally strict. Automated dependency updates, documentation edits, workflow edits, test changes and code changes all alter project state and therefore must leave a continuity breadcrumb.

### Master-state/registry edits are not authority promotions

Editing this file, the capability registry, decision index or architecture map cannot promote a serving core, merge the frozen engine, change provider authorization, publish an attempt or establish a manager decision. Those require their existing machine/release/governance mechanisms.

---

## 13. Changelog for this ledger

### 2026-09-04 — current-provider query fixed; Dastan core-root defect reproduced and repair staged

- private PR #8 changed only the narrow projection request/ledger so the query uses authority-selected `latest` instead of historical run `33719526625-1`;
- PR #8 exact-head contract `33880335918`, post-merge contract `33880420453` and projection query `33880420585` passed;
- projection artifact `9939639578` resolved current immutable run `33850307770-1` and exposed matching current PITCHSIDE rows;
- same-run provider archive exposed AIrsenal only, proving Dastan was absent upstream of the query bridge;
- canonical production diagnostic artifact `9928201488` then proved Dastan had failed with non-transient `KeyError: 'dastan'` while the serving production run remained valid because Dastan is optional/non-serving;
- code inspection proved the frozen Dastan helper was executing with repo root `.` from the mutable control-plane checkout rather than the authority-selected production-core worktree;
- staged bounded repair executes the unchanged wrapper/frozen runner from `$APEX_CORE_PATH`, verifies exact core SHA, removes stale Dastan output, and copies only newly qualified `dastan.csv` into the workspace;
- regression workflow contract added;
- affected capabilities: `GOV-002`, `PROD-001`, `PROD-007`, `OPS-006`;
- machine authority, production core, frozen PR #90, AIrsenal serving H1–H8, Dastan H1-only research status, PITCHSIDE research status, owner state, authentication, private persistence and billing/spend are unchanged;
- exact-head CI/ops and live post-merge production/provider-query evidence remain required before Dastan is called restored.

### 2026-09-04 — documentation/continuity constitution closed

- public PR #151 exact-head Apex CI `33873835393` and Apex V2 Ops Contract `33873835399` passed;
- PR #151 merged as `6a1509f766e6438a43d296e8e900518a18967959` and post-merge Apex CI `33874537255` passed;
- private PR #7 consumed/validated the single public `PRIV-*` capability semantics without creating a private registry;
- private PR #7 final exact-head contract `33876581770` passed on `fpl-apex-private-mac`;
- private PR #7 merged as `459427fe1e90565d61f8a9f6547f3876c4f3ec9a` and post-merge private contract `33876640309` passed;
- final public master-only PR #152 passed its exact-head gates and merged as `620ad5d305008c018c9ea3ccd887c9de8b510b9c`;
- machine authority, PR #90 policy, production core, serving provider/horizons, model/research behavior, private owner/auth state and billing/spend were unchanged.

### 2026-09-04 — capability/documentation constitution staged (historical staging record)

- verified public PR #150 merged at `a00f0a45d8e74d834f79cbc473a6482656b9feda` and post-merge Apex CI `33870475132` completed successfully;
- created bounded branch `agent/apex-capability-constitution` from that exact head;
- added one semantic capability registry and one decision status index without copying movable authority/current-state values;
- repurposed `APEX_ARCHITECTURE.md` as the single current cross-repository V2 map;
- reclassified older architecture and `scripts/run_apex.py` canonical-policy material as historical/non-serving rather than deleting history;
- added ref-aware capability/change-surface checker and adversarial contract tests;
- wired semantic enforcement into existing Apex CI and Apex V2 Ops Contract;
- recorded decision D032;
- machine authority, PR #90, production core, provider roles/horizons, production workflow semantics, model/research behavior, owner-private state and spending/billing policy were not changed;
- at that staging point, exact-head PR checks were the remaining acceptance gate; Era L and the closure entry above record their successful completion.

### 2026-09-04 — APEX OPERATIONAL closure

- private self-hosted runner `fpl-apex-private-mac` registered and accepted without spending-limit changes;
- exact strategy query run `33868412431` passed;
- final authority-selected `latest` strategy query `33868662109` passed;
- exact and final-latest JSON were byte-identical at SHA-256 `e50c4ebde19a2c68bfa4c38f33a6dd81f1d0922851f1e932bae522a898609d60`;
- both resolved immutable run `33850307770-1`, entry `63984`, exact 15-player owner state, £0.5m bank, 1 FT and complete transfer prices/state;
- final private contract `33868662187` passed;
- public authority remained core `c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437` with frozen PR #90 unchanged;
- historical billing blocker reclassified as closed provenance;
- public guard/tests updated to assert durable operational state rather than the obsolete billing-blocked sentence.

### 2026-09-04 — master continuity control layer introduced

- consolidated live production closure state after successful immutable run `33850307770-1`;
- recorded authority core `c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437` and frozen base `99cc7b51b0cff45462b567084cb1844cfe0a456f`;
- documented permanent PR #146 single-solve/publication-witness repair and #147 promotion;
- recorded authentication recovery and successful release evidence;
- reconciled older Project Brain documents into one canonical human continuity ledger;
- added mandatory agent startup instructions and same-change CI enforcement;
- preserved machine authority and immutable release evidence above prose in the precedence hierarchy.
