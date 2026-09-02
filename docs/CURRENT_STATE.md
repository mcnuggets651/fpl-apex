# FPL Apex — Current State

**Last updated:** 2 September 2026

Canonical machine authority: [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json).

## Production now

Apex V2 is frozen at engine SHA:

`99cc7b51b0cff45462b567084cb1844cfe0a456f`

PR #90 is the frozen clean-room engine PR. It remains open, draft and unmerged; operations must not merge, advance or modify it.

The default branch `main` is the live operations/research control plane. After the V2 authority reconciliation, the verified main merge commit is:

`138a886815c5110c9a528f93f16811e99c6a7e48`

The only serving production workflow is:

`.github/workflows/apex-v2-daily-production.yml`

**AIrsenal** is the sole serving provider for H1–H8. Apex Proprietary is shadow H1–H8; Dastan is shadow H1 only; PITCHSIDE and OpenFPL are external diagnostic/shadow providers. All challenger/research surfaces are non-serving and may not be blended, voted into production or promoted automatically.

Official FPL remains factual authority for identity, club, FPL position, price, status/availability and fixtures.

## Serving contract

An actionable recommendation comes only from the authenticated frozen Apex V2 production chain and its immutable final release. Production must have exact manager state for entry 63984, one frozen input snapshot, a qualified AIrsenal H1–H8 surface, legal exact optimisation/mechanics and successful immutable publication.

If authentication, factual authority, provider qualification, snapshot identity or immutable publication is unsafe, production fails closed. Research output cannot substitute for a missing serving release.

Legacy `scripts/run_apex.py`, Pinnacle/Elite flows and repository-generated recommendation files are historical/test compatibility surfaces, not current production authority.

## GW3 prospective research

Current canonical tournament candidate:

`apex-v2/tournament-candidate/2026-2027/33590896695-1`

Official GW3 deadline:

`2026-09-04T17:30:00Z`

PR #112 added the prospective decision-edge lab. PR #113 made it parallel/resumable using immutable per-task staging. PR #114 corrected the individual heavy-task runtime contract from 30 to 50 minutes without changing the frozen optimiser. A regression derives the 34-minute theoretical MILP allowance from frozen source and requires explicit orchestration headroom.

Corrected Decision Quality run #10 (`33643925982`) is sealing a fresh task set under control-plane SHA `e123fb312015a620795f343f503f8c214699afb4`. The authority/documentation merge in PR #115 did not modify the Decision Quality workflow or research controllers, so it does not invalidate that predeadline task set.

GW3 acceptance requires all required counterfactual decisions to be immutably sealed before the deadline, exact production-baseline reproduction, complete canonical assembly, no invented Dastan H2+ plan, non-serving research flags, clean frozen-worktree proofs and an overall green Decision Quality run. Assembly may package already sealed predeadline decisions later; it may never create a missing decision after the deadline.

## Operations health

Structurally healthy:

- Apex V2 Daily Production;
- authenticated owner-state recovery/rotation;
- deadline watcher;
- daily prospective evaluation;
- prospective tournament;
- immutable private release store boundaries.

PR #115 completed the Project Brain/generic-governance reconciliation. The machine authority, canonical documents, generic checker, tests and active workflow inventory now agree on the frozen V2 production constitution. Legacy publishers are archived outside `.github/workflows`, and the V2 Ops Contract fails if they return or if canonical authority documents revive obsolete V1/Pinnacle production claims.

## Source of truth for continuation

For substantive work:

1. read `APEX_V2_AUTHORITY.json`;
2. read this file;
3. read `APEX_MASTER_CONTEXT.md` and `APEX_OPERATING_MANUAL.md`;
4. use `APEX_V2_DAILY_OPERATIONS.md`, `APEX_V2_SAFE_EXTENSIONS.md`, `APEX_V2_PROSPECTIVE_TOURNAMENT.md` and `operations/PARALLEL_DECISION_LAB.md` for implementation details;
5. verify live `main`, PR #90 and relevant workflow/release state before changing anything.

Do not use an old GW1 squad or historical generated recommendation as current manager state. Do not invent a squad from memory.
