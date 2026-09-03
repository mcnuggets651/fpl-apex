# FPL Apex — Master Context

**Canonical Project Brain for Apex V2.** Read the machine authority first: [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json).

Immutable forensic base (`frozen_engine_sha`): `99cc7b51b0cff45462b567084cb1844cfe0a456f`

Current serving core (`production_core_sha`): `40ac0176ebdf0ce7db80b77b31dbf19623d57932`

## Mission

Produce one canonical production FPL recommendation for entry **63984** that maximises expected points under exact FPL rules while using exact authenticated manager state and failing closed when data, authentication, snapshot identity or provider qualification is unsafe.

Separately, run rigorous prospective/no-hindsight research to measure forecast quality and decision edge. Research may challenge production but cannot silently influence serving output.

## Production constitution

- Season: 2026/27.
- Immutable PR #90 forensic/base SHA: `99cc7b51b0cff45462b567084cb1844cfe0a456f`.
- Current serving code is the authority-declared `production_core_sha` above and must descend from the immutable base.
- Frozen engine PR: #90; keep it open/draft/unmerged and do not advance it for operations changes or successor promotion.
- Operations/research control plane: `main`.
- Canonical production workflow: `.github/workflows/apex-v2-daily-production.yml`.
- Sole serving champion: **AIrsenal**, H1–H8.
- Apex Proprietary: shadow H1–H8.
- Dastan: shadow H1 only.
- PITCHSIDE: external shadow/diagnostic.
- OpenFPL: diagnostic/shadow.
- Tournament/research production influence: `NONE`.
- Automatic serving promotion: forbidden.

Official FPL is factual authority for identity, club, FPL position, price, status/availability and fixtures.

## One production recommendation

The serving result is the immutable Apex V2 final produced by the authenticated production workflow using the exact authority-declared `production_core_sha`. It contains the legal action from exact current state: transfers/roll, XI, captain, vice, bench order and exact mechanics, with horizon planning/contingencies where supported by the serving-core contract.

There is no second user-facing Pinnacle, Elite, CVaR, value or challenger team. Those names survive only in historical V1 code/research or as diagnostics where explicitly labelled. Legacy `scripts/run_apex.py` and `data/generated/apex_recommendation_latest.*` are not current serving authority.

## Production lifecycle

Apex V2 Daily Production:

1. checks out exact `main` as the bounded control plane;
2. resolves `production_core_sha` and immutable `frozen_engine_sha` from machine authority;
3. proves the serving core descends from the immutable base and materializes the exact serving core in a detached worktree;
4. installs that core using its exact dependency lock when available;
5. preflights the immutable private manager store;
6. validates/recovers authentication for the configured entry;
7. creates the immutable attempt intent bound to the exact serving-core SHA;
8. captures Official FPL authority before provider work;
9. obtains fresh pinned AIrsenal H1–H8 and governed shadow surfaces;
10. re-anchors Official FPL and freezes inputs once, bound to the same serving-core SHA;
11. solves with network access disabled and checks exact architecture/mechanics and qualification;
12. publishes private prerequisites then the immutable public final, again bound to the same serving-core SHA.

No research workflow may acquire/solve/publish a serving recommendation.

## Prospective tournament and decision edge

The prospective tournament scores provider forecasts only from surfaces sealed before outcomes. GW2 remains diagnostic/non-canonical. GW3 and later canonical observations use immutable predeadline selection rules.

Decision Quality adds predeadline counterfactual FPL decisions. It reproduces the exact production baseline and can test provider H1 mechanics, challenger H1 plus AIrsenal future, availability-only overlays and pure provider plans only where genuine contiguous horizons exist. Dastan H1-only never receives an invented H2+ pure-provider plan.

Realized decision scoring includes formation-aware autosubs, goalkeeper substitution, captain-to-vice fallback, transfer hits, Triple Captain and Bench Boost. Sequential learning can create diagnostic/review evidence but cannot change serving authority automatically.

## No-hindsight law

A forecast or decision variant must be immutably committed before the relevant Official FPL deadline. A missing predeadline task stays missing forever for that candidate. Postdeadline assembly may package already committed decisions but cannot calculate a new counterfactual.

## Manager-state law

Never reconstruct the current squad from conversation history, an old screenshot, a historical generated file or a shadow provider. Use the authenticated production manager state for entry 63984. A current user-supplied private state may be evidence only where the current control plane explicitly supports it; do not bypass production governance manually.

AIrsenal worker setup team ID `1` is deliberately an upstream database-initialisation placeholder. The worker produces player forecasts and skips manager-specific transaction updates; it is not the production manager identity and must not be changed to 63984 as an operations fix.

## Change boundaries

Normal operations may change scheduling, bounded auth recovery, evaluation orchestration, non-serving research controllers and documentation/governance without modifying serving-core semantics. Changes to serving `src/`, `config/` or tests require an explicit certified-successor path, sealed assurance and deliberate `production_core_sha` promotion; they must never advance PR #90.

Never alter candidate depth, horizon, MILP precision or exact mechanics merely to make research faster. Runtime/orchestration must accommodate certified semantics instead.

## Continuity protocol

Before substantive Apex work:

1. read `APEX_V2_AUTHORITY.json`;
2. read `CURRENT_STATE.md`;
3. read this file and `APEX_OPERATING_MANUAL.md`;
4. read `APEX_V2_DAILY_OPERATIONS.md` plus the relevant V2 research/operations runbook;
5. verify live GitHub `main`, PR #90, `production_core_sha`, workflow runs and immutable release state;
6. only then implement or answer.

Repository history remains useful evidence, but it may not overrule the current V2 authority chain.
