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

## 2. Manager question / ChatGPT paths

### Classic FPL owner path

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

### FPL Draft owner path

```text
User / ChatGPT
      |
      | read continuity + capability registry + Draft runbook
      v
mcnuggets651/fpl
(private live Draft query)
      |
      +--> Official Draft public league/details/status/bootstrap
      |         |
      |         +--> exact roster
      |         +--> available / locked pool
      |         +--> public league history
      |
      v
narrow private Draft query artifact
```

Pending/open personal Draft transactions use a separate authenticated side channel so reusable credentials never move into the private query workflow:

```text
mcnuggets651/fpl-apex
(existing governed owner-auth lifecycle)
      |
      | certified bearer/cookie/refresh transport
      v
Official FPL Draft authenticated entry transaction endpoint
      |
      | allowlist + credential stripping
      v
credential-free repository_dispatch
      |
      v
mcnuggets651/fpl
(private relay validation + short-retention artifact)
      |
      v
fresh ChatGPT pending/open-waiver answer
```

Rules:

- Classic owner state is never reconstructed from conversation memory, screenshots or historical generated recommendation files;
- Draft roster/waiver state is never reconstructed from memory, screenshots or old transaction rows when the live query is required;
- `latest` is authority-first, not newest-timestamp-first;
- an explicit historical Classic run may be queried, but it is labelled historical rather than treated as current authority;
- Draft and Classic player element IDs are separate namespaces; projection joins reconcile by name + club + position;
- reusable credentials, private-auth material, commitment keys, raw authenticated Draft bodies and unfiltered private payloads never enter the public repository or public answer surface;
- an empty pending Draft queue is valid only after the authenticated endpoint succeeds and the private relay records a successful snapshot.

The detailed manager-query contract is `docs/CHATGPT_APEX_QUERY_POLICY.md`. Draft-specific procedure is `docs/APEX_DRAFT_QUERY.md`. Private implementation lives in `mcnuggets651/fpl`; the public registry records those capabilities semantically without duplicating private state.

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

The Draft query/relay path is **outside** the production solve/publish chain. It cannot create or alter a Classic serving decision and cannot submit Draft transactions.

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

### Manager-decision product contract

Apex exists to make the best owner decision, not to generate expected-points tables for their own sake. Forecasts are inputs to one manager objective: maximise expected FPL points through legal receding-horizon squad-management decisions.

The production architecture must therefore treat transfer policy as a first-class serving concern. The manager decision surface must compare, as applicable, **ROLL**, legal one-transfer moves, legal multi-transfer combinations, chained multi-Gameweek routes and points hits from the exact owner TeamState. It must preserve exact bank, free-transfer rollover, purchase-price, selling-price and squad-legality mechanics and re-solve at every deadline rather than treating a future path as a commitment.

Price movement is a state-transition constraint, not a source of fantasy points. A future price model may change which routes remain affordable and therefore their continuation value, but it must never add an arbitrary team-value bonus to the football objective.

### Required price-aware transfer-policy successor

The current authority-selected core remains the only serving implementation until an explicitly certified descendant successor is promoted through the existing governance path. However, the **required production destination** is a price-aware multi-week transfer policy with calibrated uncertainty around future market prices.

The successor should extend the future-state model so relevant players carry a calibrated transition distribution such as `P(+0.1)`, `P(no change)` and `P(-0.1)` over the actionable horizon, with wider uncertainty further from the present. Scenario state must preserve market price together with the owner's purchase price and derived selling price so future affordability obeys exact FPL mechanics.

The planner should expose route-level decision evidence rather than merely standalone player rankings, including where supportable:

- Gameweek-by-Gameweek and cumulative expected-points delta versus ROLL;
- resulting bank and free-transfer state;
- probability a preferred route remains affordable;
- probability of being priced out by target rises and/or seller falls;
- expected continuation-value loss from waiting (`price regret`);
- expected continuation-value loss from acting before additional injury/role/news information (`information regret`);
- probability each serious root action is optimal under the scenario set;
- policy stability / selection regret when alternatives are near-tied.

A research/shadow or canary implementation of this policy is a **temporary certification and promotion gate only**. It is not an acceptable terminal architecture and must not become a permanently non-serving feature that is forgotten while production continues to present shallow transfer rankings. Promotion remains deliberate and evidence-gated: no automatic authority change, no weakening of no-hindsight/replay/mechanics/privacy gates, and no change to frozen PR #90.

The private `PRIV-003` strategy surface must ultimately expose the richer authority-correct production route evidence; it must not become an independent optimiser or second serving authority.

This architecture commitment does not itself change `production_core_sha`, provider authorization or current production output. Implementation requires a governed successor change, tests, prospective/canary evidence and explicit authority promotion.

## 4. Operations plane

```text
                    +--> Auth keepalive
                    +--> Direct-auth incident diagnostic
                    +--> Authenticated Draft transaction relay
                    +--> Deadline watch
Production evidence +--> Daily prospective evaluation
                    +--> Owner brief
                    +--> Shadow-provider health
                    +--> Failed/orphan attempt audit
```

Operations capabilities support or inspect production/interaction state but do not create a second serving authority. The authenticated Draft relay shares the existing non-cancelling owner-auth concurrency boundary and emits only a credential-free private dispatch; it does not publish a public owner artifact.

Exact entry points, runbooks, tests and failure behavior are indexed by `OPS-*` capabilities in `docs/APEX_CAPABILITY_REGISTRY.yaml`.

Principal runbooks:

- `docs/APEX_V2_DAILY_OPERATIONS.md` for production-support operations;
- `docs/APEX_DRAFT_QUERY.md` for the live Draft owner query and authenticated relay.

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
- governed FPL owner-auth lifecycle;
- credential-stripping authenticated Draft relay producer;
- research-safe immutable publication;
- operations and research orchestration;
- canonical public master state, capability registry, system map and decision history.

Must not contain:

- credentials or private-auth payloads;
- authenticated raw Draft owner transaction bodies;
- exact unfiltered manager state from private releases;
- private commitment material;
- a public artifact containing owner Draft transaction state;
- a copied private semantic registry that could drift from the public one.

### Private repository — `mcnuggets651/fpl`

Owns:

- immutable private manager/provider persistence;
- authority-first Classic owner queries;
- exact multi-week strategy query output;
- live Official Draft roster/available/locked query artifacts;
- validated credential-free authenticated Draft transaction relay artifacts;
- safe manager-shape diagnostics;
- repository-scoped self-hosted execution;
- private continuity contract.

It does **not** own public serving authority. It consumes the public capability registry and validates private bindings locally; it must not create a competing registry. Reusable FPL authentication remains outside the private Draft query workflow.

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
- FPL Draft owner query/relay: `docs/APEX_DRAFT_QUERY.md`
- Research tournament: `docs/APEX_V2_PROSPECTIVE_TOURNAMENT.md`
- Parallel decision research: `docs/operations/PARALLEL_DECISION_LAB.md`
- Shadow reliability: `docs/operations/SHADOW_PROVIDER_RELIABILITY.md`

This map must remain descriptive. If it conflicts with immutable evidence or `docs/APEX_V2_AUTHORITY.json`, the higher authority wins and this document must be corrected in the same change.
