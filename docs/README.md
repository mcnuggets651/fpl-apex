# Apex Project Brain

This directory is the canonical continuity layer for the Apex FPL project.

## Mandatory read order for every new Apex session
1. [CURRENT_STATE.md](CURRENT_STATE.md) — what is true now.
2. [APEX_MASTER_CONTEXT.md](APEX_MASTER_CONTEXT.md) — mission, principles and unified architecture.
3. [APEX_DECISIONS.md](APEX_DECISIONS.md) — permanent design decisions and their reasons.
4. [APEX_CANONICAL_DECISION_POLICY.md](APEX_CANONICAL_DECISION_POLICY.md) — the only valid user-facing team-selection path.
5. [APEX_OPERATING_MANUAL.md](APEX_OPERATING_MANUAL.md) — how ChatGPT/maintainers must work on Apex.
6. `data/generated/apex_recommendation_latest.json` — the only user-facing team output.

Only after those should internal diagnostics such as Pinnacle, Elite, CVaR or solver parity be inspected.

Do not reconstruct the project from chat memory when these sources are available.

## Canonical documents
- [APEX_MASTER_CONTEXT.md](APEX_MASTER_CONTEXT.md) — permanent project context.
- [CURRENT_STATE.md](CURRENT_STATE.md) — current production state and immediate next actions.
- [APEX_DECISIONS.md](APEX_DECISIONS.md) — append-only architectural/decision history.
- [APEX_CANONICAL_DECISION_POLICY.md](APEX_CANONICAL_DECISION_POLICY.md) — one production recommendation contract.
- [APEX_ROADMAP.md](APEX_ROADMAP.md) — completed, active and future milestones.
- [APEX_ARCHITECTURE.md](APEX_ARCHITECTURE.md) — end-to-end system architecture and module responsibilities.
- [APEX_MODEL_SPEC.md](APEX_MODEL_SPEC.md) — mathematical/model specification.
- [APEX_DATA_SOURCES.md](APEX_DATA_SOURCES.md) — canonical source hierarchy and source responsibilities.
- [APEX_OPERATING_MANUAL.md](APEX_OPERATING_MANUAL.md) — mandatory operating protocol for recommendations and development.
- [APEX_CHANGELOG.md](APEX_CHANGELOG.md) — project evolution by milestone/version.
- [APEX_CHARTER.md](APEX_CHARTER.md) — principles that should not change casually.
- [SESSION_LOG.md](SESSION_LOG.md) — chronological continuity log after meaningful work sessions.
- [BENCHMARKS.md](BENCHMARKS.md) — benchmark protocol and optimiser comparisons.
- [KNOWN_ISSUES.md](KNOWN_ISSUES.md) — current limitations and unresolved risks.
- [VISION.md](VISION.md) — long-term target state.

## Memory protocol
Whenever the user says **continue Apex**, **build my team**, **give me the Apex team**, or otherwise resumes this project:

1. Load the Project Brain in the mandatory order above.
2. Read `apex_recommendation_latest.json` rather than a remembered or standalone diagnostic team.
3. If `ready_to_act=false`, report blockers rather than choosing manually among internal candidates.
4. If `ready_to_act=true`, present that recommendation as **the** Apex team.
5. Distinguish clearly between **production state**, **proposed changes**, **diagnostics**, and the **canonical recommendation**.
6. Use repositories/models as the primary decision system; use current web/news evidence only as verification for short-lived facts such as injuries, transfers, manager statements and availability.
7. Never describe an unmerged idea as production.
8. Never present Pinnacle, Elite, CVaR, Value or ownership-led squads as separate Apex recommendations.
9. Record material architectural decisions in `APEX_DECISIONS.md` and session progress in `SESSION_LOG.md`.

Historical standalone selection philosophies are archived under `archive/selection_approaches/`.

This index exists specifically to prevent context drift and repeated re-explanation across conversations.
