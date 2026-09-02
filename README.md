# FPL Apex — Apex V2

Apex is a reproducible 2026/27 Fantasy Premier League decision system for entry **63984**. Its production goal is one canonical legal maximum-EV recommendation with exact current manager state, transfers/roll, XI, captain, vice, bench order, near-horizon tactics and longer conditional scenarios, while failing closed when data/auth/state is unsafe.

The machine-readable repository authority is [`docs/APEX_V2_AUTHORITY.json`](docs/APEX_V2_AUTHORITY.json).

## Production constitution

- Frozen certified engine: `99cc7b51b0cff45462b567084cb1844cfe0a456f`.
- Frozen engine PR #90 remains draft/open/unmerged and is not an operations branch.
- `main` is the operations/research control plane; it does not redefine frozen model semantics.
- Canonical production workflow: `.github/workflows/apex-v2-daily-production.yml`.
- **AIrsenal** is the sole serving champion H1–H8.
- Apex Proprietary, Dastan, PITCHSIDE and OpenFPL are shadow/diagnostic only.
- Research has no serving authority and `production_influence = NONE`.
- Official FPL is factual authority for player identity, club, position, price, status/availability and fixtures.
- No blending, voting, silent fallback or automatic challenger promotion is permitted.

## Serving interface

Production authority is the immutable Apex V2 final release created by the frozen engine and its authenticated V2 workflow. The workflow freezes inputs once, verifies Official FPL authority around provider acquisition, solves offline, checks exact FPL mechanics and publishes immutably.

Legacy repository-generated files such as `data/generated/apex_recommendation_latest.*`, Pinnacle/Elite outputs and `scripts/run_apex.py` are retained for history, compatibility and tests. They are **not** the current serving interface.

## Operations and research separation

Apex V2 deliberately separates production from evidence generation:

- `.github/workflows/apex-v2-daily-production.yml` — sole serving production path.
- `.github/workflows/apex-v2-auth-keepalive.yml` — authentication maintenance only.
- `.github/workflows/apex-v2-deadline-watch.yml` — deadline-aware production dispatch only.
- `.github/workflows/apex-v2-daily-evaluation.yml` — realized prospective evaluation only.
- `.github/workflows/apex-v2-prospective-tournament.yml` — sealed non-serving model tournament.
- `.github/workflows/apex-v2-decision-quality.yml` — sealed non-serving counterfactual decision-edge lab.

Retired V1/Pinnacle publishers are stored under `archive/workflows/` and cannot execute as GitHub Actions.

## Prospective learning

Apex evaluates challengers without hindsight. Forecast and decision variants must be committed before the relevant Official FPL deadline. Missing predeadline decisions remain missing; they are never reconstructed after outcomes are known.

The tournament evaluates forecast quality separately from the Decision Quality lab, which asks whether a challenger disagreement would have changed the actual FPL decision and whether that precommitted counterfactual later scored better. Neither layer can change serving authority automatically.

## Repository checks

Required generic CI contexts remain:

- `test`
- `contract`
- `readiness`

The Apex V2 Ops Contract additionally executes operations regressions against the exact frozen evaluator and rejects operations changes that cross into frozen `src/`, `config/` or `tests/` semantics.

## Project Brain startup

Read in this order:

1. [`docs/APEX_V2_AUTHORITY.json`](docs/APEX_V2_AUTHORITY.json)
2. [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md)
3. [`docs/APEX_MASTER_CONTEXT.md`](docs/APEX_MASTER_CONTEXT.md)
4. [`docs/APEX_OPERATING_MANUAL.md`](docs/APEX_OPERATING_MANUAL.md)
5. [`docs/APEX_V2_DAILY_OPERATIONS.md`](docs/APEX_V2_DAILY_OPERATIONS.md)
6. [`docs/APEX_V2_PROSPECTIVE_TOURNAMENT.md`](docs/APEX_V2_PROSPECTIVE_TOURNAMENT.md)
7. [`docs/operations/PARALLEL_DECISION_LAB.md`](docs/operations/PARALLEL_DECISION_LAB.md)

Then verify live GitHub state and the relevant immutable release before answering an actionable FPL question. Never reconstruct a squad from conversation memory when authenticated production state is required.

## Legacy development surfaces

The repository contains extensive V1/V1.5 implementation, diagnostics and historical research. They remain useful for tests and forensic comparison but cannot be presented as alternate current Apex teams or production entrypoints. Historical workflow YAML is preserved under `archive/workflows/` specifically so it cannot execute.

## Licence

Apex is MIT licensed. External providers/workers retain their own licences and terms.
