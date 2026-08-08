# Apex FPL — Session Log

Append concise records after meaningful project sessions. This is continuity context, not a replacement for Git history.

## 2026-08-08 — Elite xP-anchor correction
### Context
The first live Elite 10.0 output exposed a conceptual flaw: percentile/rank utility was being optimised directly. The unrestricted Elite squad scored 313.851 raw xP versus 319.582 for maximum-EV (5.731 xP / ~1.8% regret), and the report displayed Elite utility values under a `gw1_xp` heading.

### Decision
Preserve Pinnacle ensemble xP as the mathematical anchor. Retain the 35/20/15/10/10/5/5 Elite evidence profile only as a controlled modifier around raw xP.

### Implementation
- Added `elite_decision_xp = xp * (1 + bounded Elite modifier)`.
- Initial modifier is capped at ±5% per player/Gameweek.
- Elite optimiser now selects on `elite_decision_xp`, not standalone `elite_score`.
- Raw xP rescore remains mandatory.
- Elite report now uses the raw-xP-rescored squad/XI when displaying `gw1_xp`.
- Haaland and no-Haaland scenarios use the same xP-anchored surface.
- Recorded the architecture decision in `APEX_DECISIONS.md` and updated `CURRENT_STATE.md`.

### Next actions
1. Pass CI and merge the xP-anchor correction.
2. Generate one synchronized live snapshot.
3. Compare Pinnacle maximum-EV, Elite unrestricted, Haaland and no-Haaland on raw xP and robustness.
4. Compare the winning structures against the user's private draft.
5. Publish the final Apex squad only after this comparison.

## 2026-08-08 — Project Brain creation
### Context
Repeated project conversations were losing continuity between current production state, proposed architecture and squad recommendations.

### Actions
- Established a canonical documentation system.
- Defined startup/continuity protocol.
- Recorded current Pinnacle/Elite relationship.
- Recorded Elite 10.0 weighting and safeguards.
- Separated production, validation-needed and proposed states.
- Added benchmark, known-issues and vision registers.

### Current state
Elite 10.0 is merged. The next modelling task is to run/inspect its latest live output and compare it against Pinnacle rather than continue theoretical squad tweaking.

### Next actions
1. Validate latest Elite output.
2. Benchmark raw xP and Elite utility versus Pinnacle.
3. Compare the user's current private draft with both engines.
4. Only then decide whether Meta optimisation is necessary.

## 2026-08-07 — Elite 10.0 implementation
### Decision
Correct the observed low-ceiling/value bias without replacing canonical expected points.

### Implementation
Added an Elite utility with 35/20/15/10/10/5/5 weighting and raw-xP regret reporting. PR #6 passed the configured Apex FPL workflow and was merged.

### Lesson
A green CI run proves configured software checks passed; it does not prove a new decision objective improves FPL outcomes. Benchmarking remains mandatory.
