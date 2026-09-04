# FPL Apex — Current V2 System Map

> **CURRENT ARCHITECTURE MAP**
>
> This is the single current cross-repository architecture map for FPL Apex. It describes relationships and boundaries, not movable serving state. For current serving facts always read `docs/APEX_V2_AUTHORITY.json`; for current human continuity/history read `docs/FPL_APEX_MASTER_STATE.md`; for capability ownership and change surfaces read `docs/APEX_CAPABILITY_REGISTRY.yaml`.

## 1. Authority hierarchy

```text
Immutable release evidence + live GitHub / Official FPL facts
                         |
                         v
             APEX_V2_AUTHORITY.json
             (machine serving authority)
                         |
                         v
            FPL_APEX_MASTER_STATE.md
             (human continuity ledger)
                         |
                         v
          APEX_CAPABILITY_REGISTRY.yaml
      (semantic capability/change-surface index)
                         |
                         v
        This system map + capability runbooks
                         |
                         v
       Decision history / code / tests / memory
```

The capability registry does **not** select a production core, provider, run, release, squad or current health state. It points to the machine authority and to the code/runbooks/tests that implement each capability.

## 2. Manager question / ChatGPT path

```text
User / ChatGPT
      |
      | read continuity + machine authority
      v
mcnuggets651/fpl-apex
(public authority/control plane)
      |
      | identify current authority-correct immutable public attempt
      v
approved private query boundary
mcnuggets651/fpl
      |
      | authority-first release selection
      | digest + attestation + identity + TeamState checks
      v
authority-correct immutable private manager release
      |
      | narrow safe response only
      v
verified squad / transfer / strategy answer
```

Rules:

- owner state is never reconstructed from conversation memory, screenshots or historical generated recommendation files;
- `latest` is authority-first, not newest-timestamp-first;
- an explicit historical run may be queried, but it is labelled historical rather than treated as current authority;
- credentials, private-auth material, commitment keys and unfiltered private payloads never enter the public repository or public answer surface.

The detailed manager-query contract is `docs/CHATGPT_APEX_QUERY_POLICY.md`. Private implementation lives in `mcnuggets651/fpl`; the public registry records that capability semantically without duplicating private state.

## 3. Canonical production path

```text
main control plane
      |
      +--> APEX_V2_AUTHORITY.json
      |       |
      |       +--> frozen_engine_sha
      |       |    forensic lineage only; NEVER_MERGE_OR_ADVANCE
      |       |
      |       +--> production_core_sha
      |            exact serving code selected independently
      |
      v
authority-declared daily production workflow
      |
      +--> private owner authentication / TeamState boundary
      +--> Official FPL factual authority
      +--> provider acquisition
      |      |
      |      +--> AIrsenal: serving role only as declared by machine authority
      |      +--> other declared providers: shadow/research only
      |
      v
one frozen production snapshot
      |
      | network disabled during solve
      v
one legal maximum-EV production solve
      |
      v
exact FPL mechanics + certification
      |
      v
deterministic publication witness
      |  (must not rerun optimisation)
      |
      +--> immutable research-safe public release
      |
      +--> linked immutable private manager/provider release
```

The control plane on `main` orchestrates and governs production. The serving implementation is materialised from the exact `production_core_sha` declared by machine authority. Therefore a path that exists in the serving core but not on mutable `main` is not missing; capability/path validation must resolve against the correct authority ref.

### Production invariants

- `.github/workflows/apex-v2-daily-production.yml` is the canonical production workflow only while machine authority says so.
- Official FPL is factual authority for identity, club, FPL position, price, status/availability, fixtures/deadlines and authenticated manager mechanics.
- Production consumes one frozen snapshot.
- Network access is disabled during solve.
- Production executes the legal maximum-EV path defined by the authority-selected core.
- Exact XI/captain/vice/bench/transfer mechanics are certified before final publication.
- Publication is witness-only and cannot rerun the optimiser.
- Public/private immutable identities must link correctly.
- No shadow/research provider may silently blend, vote, fall back or auto-promote into serving.

Current provider roles/horizons are intentionally **not copied here**; read `docs/APEX_V2_AUTHORITY.json`.

## 4. Operations plane

```text
                    +--> Auth keepalive
                    +--> Direct-auth incident diagnostic
                    +--> Deadline watch
Production evidence +--> Daily prospective evaluation
                    +--> Owner brief
                    +--> Shadow-provider health
                    +--> Failed/orphan attempt audit
```

Operations capabilities support or inspect production but do not create a second serving authority. Their exact entry points, runbooks, tests and failure behavior are indexed by `OPS-*` capabilities in `docs/APEX_CAPABILITY_REGISTRY.yaml`.

The principal live operations runbook is `docs/APEX_V2_DAILY_OPERATIONS.md`.

## 5. Research plane and hard serving barrier

```text
immutable pre-deadline production evidence
                |
                +--> Prospective provider tournament
                |
                +--> Parallel Decision Quality lab
                |
                +--> Shadow-provider reliability/health
                |
                +--> Legacy projection/team-strength validation
                |
                v
post-outcome scoring / sequential learning evidence
                |
                v
human governance review
                |
                X  NO automatic promotion
                X  NO production influence
                X  NO serving authorization
                |
                v
only an explicit future governance/authority change could alter serving
```

Every active research capability must machine-declare:

- `production_influence = NONE`;
- `serve_authorized = false`;
- `automatic_promotion = false`.

`docs/APEX_CAPABILITY_REGISTRY.yaml` and CI enforce those declarations against the current machine-authority research boundary.

Key runbooks:

- `docs/APEX_V2_PROSPECTIVE_TOURNAMENT.md`;
- `docs/operations/PARALLEL_DECISION_LAB.md`;
- `docs/operations/SHADOW_PROVIDER_RELIABILITY.md`.

## 6. Two-repository privacy boundary

### Public repository — `mcnuggets651/fpl-apex`

Owns:

- machine serving authority;
- public control plane/workflows;
- authority-selected production-core pointer;
- research-safe immutable publication;
- operations and research orchestration;
- canonical public master state, capability registry, system map and decision history.

Must not contain:

- credentials or private-auth payloads;
- exact unfiltered manager state from private releases;
- private commitment material;
- a copied private semantic registry that could drift from the public one.

### Private repository — `mcnuggets651/fpl`

Owns:

- immutable private manager/provider persistence;
- authority-first owner queries;
- exact multi-week strategy query output;
- safe manager-shape diagnostics;
- repository-scoped self-hosted execution;
- private continuity contract.

It does **not** own public serving authority. A later bounded private governance change may consume the public capability registry and validate private bindings locally; it must not create a competing registry.

## 7. Capability/documentation constitution

The permanent documentation hierarchy is:

```text
Immutable evidence
  -> Machine authority
  -> Master state
  -> Capability registry
  -> Current system map
  -> Capability runbooks/contracts
  -> Decision history
  -> Code/tests
  -> Conversation memory
```

Responsibilities are intentionally separated:

- `APEX_V2_AUTHORITY.json`: movable serving authority and constitution;
- `FPL_APEX_MASTER_STATE.md`: dated human continuity, accepted evidence and next state;
- `APEX_CAPABILITY_REGISTRY.yaml`: stable semantic capability IDs, entry points, dependencies, privacy, runbooks, tests and change surfaces;
- `APEX_ARCHITECTURE.md`: relationships and data/control flow;
- `APEX_DECISION_INDEX.yaml`: machine-readable status/supersession index;
- `APEX_DECISIONS.md`: append-only rationale/history;
- runbooks: operational procedure for a bounded capability.

Do not copy current production-core SHAs, workflow run IDs, current squad/bank/FT/prices, live provider health, or latest release identity into the capability registry or architecture map.

## 8. Change-control flow

```text
read master + machine authority + registry
                |
                v
declare affected Apex capability IDs in PR metadata
                |
                v
identify invariants / decisions / authority impact
                |
                v
make bounded code/docs/test change
                |
                v
update master state in same change
                |
                v
capability checker:
  schema + workflow/script coverage
  ref-aware entry-point existence
  research/serving/privacy boundaries
  changed paths <-> declared capability IDs
  decision-index completeness
                |
                v
Apex CI + Apex V2 Ops Contract
                |
                v
runtime acceptance where the capability requires it
```

PR metadata is semantic input to CI, not a checkbox substitute:

```text
Apex-Capabilities: GOV-003, OPS-003
Apex-Authority-Changed: no
Apex-Invariants-Changed: none
Apex-Decisions-Reopened: none
```

The checker compares the declaration with the actual changed paths registered under capability `change_surface`. Unregistered active workflows and `scripts/apex_v2_*.py` fail the contract.

## 9. Legacy and historical surfaces

`docs/ARCHITECTURE.md`, `scripts/run_apex.py`, old generated recommendation/answer-context files and the former Pinnacle/Elite/static selector authority chain are historical/non-serving under V2. They may remain useful as forensic or research context, but they cannot answer “what is production?” or publish the current Apex recommendation.

The machine authority's `legacy` section and `LEG-*` registry capabilities own this classification. Archived workflows under `archive/workflows/` remain forensic source, not executable production.

## 10. Where to go next

- Current mutable serving facts: `docs/APEX_V2_AUTHORITY.json`
- Current human continuity/status: `docs/FPL_APEX_MASTER_STATE.md`
- Capability discovery/change ownership: `docs/APEX_CAPABILITY_REGISTRY.yaml`
- Decision status: `docs/APEX_DECISION_INDEX.yaml`
- Decision rationale: `docs/APEX_DECISIONS.md`
- Daily production/operations: `docs/APEX_V2_DAILY_OPERATIONS.md`
- Manager-query rules: `docs/CHATGPT_APEX_QUERY_POLICY.md`
- Research tournament: `docs/APEX_V2_PROSPECTIVE_TOURNAMENT.md`
- Parallel decision research: `docs/operations/PARALLEL_DECISION_LAB.md`
- Shadow reliability: `docs/operations/SHADOW_PROVIDER_RELIABILITY.md`

This map must remain descriptive. If it conflicts with immutable evidence or `docs/APEX_V2_AUTHORITY.json`, the higher authority wins and this document must be corrected in the same change.
