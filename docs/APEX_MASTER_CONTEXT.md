# Apex FPL — Master Context

**Canonical project brain. Read this before making an Apex recommendation or architectural change.**

Operating authority: [`APEX_OPERATING_MANUAL.md`](APEX_OPERATING_MANUAL.md).  
Current state: [`CURRENT_STATE.md`](CURRENT_STATE.md).

## Mission

Build the strongest auditable Fantasy Premier League decision engine possible: maximise expected FPL points under exact FPL rules while explicitly measuring uncertainty, robustness, decision regret and evidence quality.

## Repository

- Repository: `mcnuggets651/fpl-apex`
- Production branch: `main`
- Personal FPL entry: `63984`
- Season: 2026/27

## Production authority chain

1. **Official FPL — factual truth.** Current Official player ID, club, FPL position, price, availability/status, fixtures and rules/mechanics inputs.
2. **AIrsenal — canonical statistical xP.** Production `xp` equals validated AIrsenal xP directly. Missing/stale/incomplete AIrsenal blocks. There is no silent Apex fallback.
3. **Current football evidence — availability/minutes/role context.** Attributable current evidence can constrain eligibility or uncertainty; it cannot invent unsourced xP bonuses.
4. **Apex optimiser — decision authority.** Legal squad/current-team optimisation, exact XI/captain/vice/bench/autosubs and receding-horizon first-action selection.
5. **Apex proprietary forecast, Understat, FPL Core and other challengers — shadow/enrichment.** Preserve signal and diagnostics without production forecast authority unless prospectively promoted.
6. **Prospective calibration — promotion judge.** Freeze forecasts before deadlines, score later outcomes out of sample, and require explicit evidence before changing authority or weights.

## Non-negotiable principles

1. Official FPL wins every current identity/price/club/position/fixture conflict.
2. Never select a squad from memory or generic FPL opinion when canonical repository outputs exist.
3. `xp` is a forecast, not a fact. Current production `xp` is AIrsenal exactly.
4. Expected minutes/start/appearance probabilities remain forecast evidence; future certainty may not be fabricated.
5. Missing canonical AIrsenal coverage fails closed; Apex shadow xP is not a production fallback.
6. FPL Core/Understat enrichment failures must be disclosed but cannot masquerade as canonical-xP failures while the production path is independent of them.
7. One legal optimiser/decision path produces one user-facing recommendation.
8. CVaR, regret, parity, Elite and static exact-horizon surfaces are diagnostics/challengers, not competing user-facing teams.
9. Ownership is excluded from the pure maximum-points objective.
10. A current recommendation requires reproducible sealed inputs, exact mechanics, final evidence identity and a green answer context.
11. No projection expert, blend, threshold or named-player adjustment is promoted by subjective preference.
12. Football randomness is irreducible; confidence must never be presented as certainty.

## One user-facing recommendation

The only user-facing decision files are:

- `data/generated/apex_answer_context.json`
- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`

If `safe_to_act=false` or `ready_to_act=false`, Apex has no actionable team. Historical squads and internal diagnostic outputs are not fallbacks.

The canonical production command remains:

```bash
python scripts/run_apex.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
```

## Decision lifecycle

- **Pre-GW1 historical mode:** `adaptive_gw1_launch_with_transfer_option_value` remains retained for replay/history.
- **Current in-season mode:** `receding_horizon_current_team_maximum_ev` starts from the manager's exact current squad, bank, selling values and free-transfer state; it may solve a future path but publishes only the first currently executable action.

GW1 is complete. The expired one-off GW1 execution workflow is archived and must not be used as an active production path.

## Forecast promotion

Apex proprietary xP is currently shadow-only. Future challenger or ensemble authority requires genuine prospective evidence. Existing governance requires at least 8 completed genuine Gameweeks and >=200 active rows, chronological validation, Gameweek-block uncertainty/confidence analysis, cohort diagnostics and explicit review. No automatic promotion occurs.

At the 28 August 2026 audit, the prospective calibration report still had 0 completed genuine Gameweeks / 0 active rows, so no challenger has earned production authority.

## V2 boundary

Draft PRs #67–#88 contain a valuable stacked V2 architecture programme but are not production. Their latest documentation still assumes the retired fixed three-way forecast blend, so that stack must be rebased/requalified against the current AIrsenal-only production authority before future merge.

PR #66 is superseded V1 archaeology/regression material and must not be merged.

## Continuity protocol

Before substantive Apex work read, in order:

1. `docs/CURRENT_STATE.md`
2. this file
3. `docs/APEX_DECISIONS.md`
4. `docs/APEX_CANONICAL_DECISION_POLICY.md`
5. `docs/APEX_OPERATING_MANUAL.md`
6. `data/generated/apex_answer_context.json`

Then inspect sealed/internal diagnostics only when needed. Repository state outranks chat history.

## Related documents

- [Operating manual](APEX_OPERATING_MANUAL.md)
- [Current state](CURRENT_STATE.md)
- [Canonical decision policy](APEX_CANONICAL_DECISION_POLICY.md)
- [Architecture](APEX_ARCHITECTURE.md)
- [Data sources](APEX_DATA_SOURCES.md)
- [Model specification](APEX_MODEL_SPEC.md)
- [Decisions](APEX_DECISIONS.md)
- [Benchmarks](BENCHMARKS.md)
- [Known issues](KNOWN_ISSUES.md)
- [Session log](SESSION_LOG.md)
