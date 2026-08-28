# Generated Apex outputs

## User-facing authority

Read `apex_answer_context.json` **first**. It is the gate for every Apex-labelled answer.

A recommendation is user-facing only when the same current production run has:

- `apex_answer_context.json` with `safe_to_act=true` and `ready_to_act=true`;
- `apex_recommendation_latest.json`;
- `apex_recommendation_latest.md`.

If the answer context is absent, stale or non-actionable, there is no current Apex recommendation. Do not fall back to an older team.

## Internal / legacy outputs

These files may remain because they are useful for diagnostics, replay, provenance or learning, but they are **not** separate recommendations:

- `pinnacle_latest.*` — internal exact-horizon/readiness/robustness diagnostic;
- `elite_latest.*` — internal epsilon/Elite diagnostic;
- `apex_latest.*` — legacy/base diagnostic snapshot retained for internal compatibility/history;
- `solver_parity.*` — independent optimisation assurance;
- `airsenal.csv` — production projection-worker surface, not a selected team;
- calibration/history outputs — learning diagnostics;
- DecisionBundle contents — sealed internal production surface.

Current production statistical xP is AIrsenal-only. Apex proprietary xP is shadow evidence. Generated internal files must not be interpreted using the retired fixed production blend.

Historical outputs remain recoverable through Git and durable history directories; they do not become current merely because their filename contains `latest`.
