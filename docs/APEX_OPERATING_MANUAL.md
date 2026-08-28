# Apex FPL — Operating Manual

**This is the single authoritative operating document.** Other usage, state, roadmap and known-issues documents must link here and may not redefine the answer contract, authority chain or source criticality.

## Purpose

Define how ChatGPT and operators work on Apex without reconstructing the project from memory or allowing stale artifacts to become authority.

## Mandatory startup sequence

For any substantive Apex request:

1. Read `docs/CURRENT_STATE.md`.
2. Read `docs/APEX_MASTER_CONTEXT.md`.
3. Read `docs/APEX_DECISIONS.md`.
4. Read `docs/APEX_CANONICAL_DECISION_POLICY.md`.
5. Inspect `data/generated/apex_answer_context.json`. It is the only permitted input for an Apex-labelled recommendation.
6. Verify freshness, Official snapshot identity, decision-bundle identity, source health, model/provider versions, all-player truth, solver/parity, exact mechanics, final selected-player evidence and strategy state.
7. Inspect internal diagnostics only to explain a blocker or improve the engine.
8. Use live research only as labelled current evidence for injuries, suspensions, transfers, roles, lineups and set pieces; it cannot silently replace the canonical contract.
9. For architecture/model changes, inspect the exact current GitHub branch, implementation and tests before acting.

Repository and workflow evidence outrank conversation memory.

## Production authority chain

Authority is capability-specific:

1. **Official FPL — factual truth.** Current player ID, club, FPL position, price, Official status/availability, fixture/deadline identity and public FPL state.
2. **AIrsenal — production statistical xP.** Canonical production `xp` equals validated AIrsenal xP exactly. Missing/stale/incomplete AIrsenal is a hard blocker. There is no silent Apex fallback.
3. **Current football evidence — availability/minutes/role context.** Attributable evidence can constrain eligibility or uncertainty. It cannot invent unsourced expected points.
4. **Apex optimiser — decision authority.** Legal squad/current-team optimisation, exact XI/captain/vice/bench/autosubs, parity and receding-horizon first-action selection.
5. **FPL Core, Understat, Apex proprietary xP and other challengers — enrichment/shadow.** Their health and disagreement remain visible, but they do not own canonical production xP unless prospectively promoted.
6. **Prospective calibration — promotion judge.** Forecast authority changes only after genuine frozen-before-deadline evidence and explicit review.

Optional enrichment failure cannot masquerade as a production failure when the active production path is independent of that source. Conversely, a real factual/canonical/mechanics/publication dependency remains fail-closed.

## Closed-answer contract

Every substantive FPL question is routed before answering. Best-team questions require the current canonical final strategy; transfers require exact current manager state and a receding-horizon solve; player-role questions require a current player evidence dossier; project-status claims require GitHub/workflow evidence.

If the required artifact is absent, stale or non-actionable, report the blocker. Never invent or manually repair a squad.

For a user-facing recommendation, `safe_to_act` and `ready_to_act` must both be true. Hard blockers include, where applicable:

- stale/mismatched Official FPL truth;
- incomplete current Official player factual coverage;
- stale/unhealthy/incomplete AIrsenal production xP coverage;
- invalid current manager state/finance;
- invalid evidence/provenance for a decision-critical claim;
- mismatched or corrupt DecisionBundle identity;
- incomplete/inconclusive required optimisation or parity;
- invalid exact FPL mechanics;
- final selected-player evidence mismatch;
- stale/inconsistent publication state.

FPL Core/Understat/internal shadow-model outages are warnings unless a promoted production component explicitly depends on them.

## EV-first evidence policy

The production eligibility rule is **adverse-evidence-only** pre-solve.

Expected minutes, start probability, appearance probability and role uncertainty already belong inside forecasts/scenarios. They must not be converted into a second hidden preference for supposedly safe minutes.

A player may be removed from XI/captain eligibility only when attributable current evidence justifies it, including:

- Official adverse availability/suspension;
- decision-grade negative role/availability evidence;
- an unresolved material contradiction between supported current evidence.

Low numerical confidence by itself is diagnostic rather than exclusionary. Set-piece hierarchy is ordinal evidence unless a literal share is independently sourced. Stale/unverifiable overrides are rejected.

## All-player truth requirement

For every current Official FPL player, production requires:

- complete unique Official identity;
- current club/FPL-position/price/status factual mapping;
- complete canonical player/Gameweek projection-pair coverage;
- complete required AIrsenal player/Gameweek xP coverage;
- explicit fact/override/inference/forecast semantics for decision-sensitive fields;
- no unsourced literal set-piece shares.

FPL Core player-ID coverage remains monitored enrichment quality but is not currently a release-blocking all-player requirement.

Future minutes, roles, lineups and xP remain forecasts. Literal certainty must not be manufactured.

## If the user asks for “the best team”

1. Load `data/generated/apex_answer_context.json`.
2. Do not compare several internal Apex approaches and make a fresh subjective choice.
3. If `safe_to_act=false` or `ready_to_act=false`, report blockers and do not invent a team.
4. If actionable, present `production_result` as **the** Apex recommendation.
5. Report XI, captain, vice and bench order from the final contract.
6. Explain players using the final selector and `final_selected_player_evidence`.
7. Pinnacle/static exact-horizon, Elite, CVaR, regret and parity are diagnostics only.
8. Show forced scenarios only when explicitly requested and label them as scenarios.

## Canonical command and publication

The production entrypoint is:

```bash
python scripts/run_apex.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
```

The one-way production flow is:

1. acquire/seal current Official truth and manager state;
2. validate fresh complete AIrsenal production projections;
3. ingest evidence/enrichment with explicit health/provenance;
4. seal the DecisionBundle;
5. run diagnostic/assurance layers on that same bundle;
6. assemble non-actionable staging;
7. run all-player truth;
8. apply one final strategy selector;
9. exact-rescore current FPL mechanics;
10. rebuild evidence for the actual final selection;
11. build the final answer context;
12. set `ready_to_act=true` only if all required gates pass.

The only user-facing files are:

- `data/generated/apex_answer_context.json`
- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`

`pinnacle_latest.*`, `elite_latest.*`, shadow forecasts and research reports are internal evidence only.

## Final strategy policy

The two retained selectors are:

- `adaptive_gw1_launch_with_transfer_option_value` — historical/pre-GW1 launch selector;
- `receding_horizon_current_team_maximum_ev` — current in-season selector.

GW1 is complete. Normal live operation is now the receding-horizon current-team selector: start from the exact permanent squad, bank, selling values and free transfers; solve legal option value; publish only the first newly solved action; treat later moves as contingencies to rebuild next deadline.

The one-off `gw1-final-2026.yml` workflow is archived and must not be restored to the active production surface simply for convenience.

## If the user shows a current team

Treat a screenshot/manual team as a private-current-state candidate only if it is newer than the public snapshot. Reconcile it exactly with Official identity/prices and manager-state mechanics. Do not turn it into a manual team-selection override.

## If the user asks about project status

Check GitHub directly and distinguish:

- **Production now** — merged/running/current user-facing outputs;
- **In progress** — branch/PR code and experiments;
- **Shadow/research** — non-authoritative model/data evidence;
- **Proposed** — unimplemented ideas.

Never describe a branch, open PR, test fixture or synthetic V2 proof as production.

## If changing the forecast/model

- Preserve production AIrsenal authority unless the change is an explicit provider-promotion decision.
- Keep facts, forecasts, enrichment and selection logic separate.
- Add focused and adversarial tests.
- Benchmark against frozen prospective evidence rather than preferred-player intuition.
- Record durable decisions.
- Use branch/PR discipline for non-trivial changes.
- Do not merge solely because engineering CI is green; verify modelling intent and decision impact.
- Do not introduce a second user-facing team-selection path.
- Do not hand-tune a named player.
- Do not introduce subjective forecast weights.

## Prospective learning and promotion

Production and shadow forecasts must be frozen before deadlines with provider/version, Official snapshot, player/GW and forecast-time identity. Outcome data joins only after the event.

Current promotion governance requires at least:

- 8 completed genuine prospective Gameweeks;
- >=200 active rows;
- chronological/walk-forward comparison;
- Gameweek-block confidence/uncertainty analysis;
- cohort diagnostics and relevant ablations;
- explicit review.

No automatic promotion is allowed. At the 28 August 2026 audit, calibration still had zero completed genuine Gameweeks and zero active rows. The missing/empty deadline archive must be repaired before claiming prospective learning is operational.

## FPL Core operating rule

FPL Core is enrichment. Its moving upstream may be pinned only after candidate semantic/identity validation. The refresh workflow must install Apex before calling publication invalidation, must verify the `apex_fpl.services.publication` import, and must not weaken candidate validation simply to move the pin.

A changed Core enrichment pin may still invalidate an older published decision for provenance consistency, even though Core is not canonical xP authority; the next production solve then republishes explicitly against the changed enrichment surface.

## Understat operating rule

Understat is enrichment/shadow. HTTP 200 with missing/empty football payload is unhealthy. Understat outages are disclosed but are not production blockers while canonical AIrsenal xP is independent. Any future production use requires explicit prospective promotion and dependency reclassification.

## V2 stack rule

Draft PRs #67–#88 remain a separate withheld architecture programme. Engineering certification is not production authority. Before any V2 merge/cutover, the stack must be rebased/requalified against the current production forecast authority because later V2 docs still contain the retired fixed three-way blend assumption.

PR #66 is superseded archaeology/regression material and must not be merged.

## Architecture freeze

After the current authority cutover, routine operation is **not** another architecture cycle.

Routine work is:

- refresh Official FPL;
- refresh AIrsenal;
- validate enrichment sources;
- ingest current football evidence;
- re-solve before each deadline;
- archive frozen forecasts/decisions;
- score outcomes after events;
- evaluate challengers prospectively.

Architecture reopens only when:

1. a reproducible production defect violates the contract;
2. a required upstream changes semantics so the engine cannot reconcile safely;
3. a bounded challenger demonstrates superior predictive and decision-level validity under the promotion gates.

A surprising player or one poor Gameweek is not sufficient reason to redesign the engine.

## Anti-drift rules

Do not:

- start from generic web lists;
- reconstruct old squads from chat/history;
- optimise only points-per-million;
- force premiums or cheap picks by reputation/value;
- use ownership in the pure maximum-points objective;
- present diagnostic surfaces as competing recommendations;
- confuse uncertainty with certainty;
- claim a workflow/PR is green without inspecting it;
- turn ordinal rank into invented probability;
- let missing AIrsenal silently fall back to Apex;
- let optional Core/Understat enrichment become a false hard blocker;
- weaken identity, price, solver parity, statistical truth, exact mechanics or freshness protections merely to obtain green CI.

## Documentation maintenance

After a meaningful architecture/model milestone update:

- `CURRENT_STATE.md`
- `PROJECT_STATUS.md`
- `SESSION_LOG.md`
- `APEX_CHANGELOG.md`
- `APEX_DECISIONS.md` for durable decisions
- `BENCHMARKS.md` for new performance evidence
- `KNOWN_ISSUES.md` for limitations discovered/resolved
- `APEX_CANONICAL_DECISION_POLICY.md` when the single production decision contract changes
- `APEX_ARCHITECTURE.md`, `APEX_DATA_SOURCES.md` and `APEX_MODEL_SPEC.md` when authority/dependency semantics change
