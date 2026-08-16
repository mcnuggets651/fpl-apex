# Apex FPL — Operating Manual

**This is the single authoritative operating document.** Other usage, state,
roadmap and known-issues documents must link here and may not redefine the answer
contract or source order.

## Purpose

This file defines how ChatGPT or any operator should work on Apex without repeatedly reconstructing context.

## Mandatory startup sequence

For any substantive Apex request:

1. Read `docs/CURRENT_STATE.md`.
2. Read `docs/APEX_MASTER_CONTEXT.md`.
3. Read `docs/APEX_DECISIONS.md`.
4. Read `docs/APEX_CANONICAL_DECISION_POLICY.md`.
5. Inspect `data/generated/apex_answer_context.json`. It is the only permitted input for an Apex-labelled answer.
6. Verify `safe_to_act`, run age, decision-bundle ID, material input hashes, source health, model versions, all-player truth coverage, CVaR, selection regret, solver parity, final selected-player evidence and strategy state.
7. Only inspect internal diagnostics to explain a blocker or improve the engine.
8. Use live research only as a labelled gap-fill for injuries, transfers, roles and lineups; it cannot silently override the canonical contract.
9. If code/architecture is changing, read the relevant model/architecture docs and current implementation.

## Closed-answer contract

Every substantive FPL question is routed before answering. Best-team questions require the canonical final strategy; player-role questions require a player evidence dossier; player comparisons require one matched snapshot plus appropriate decision evidence; transfers require current entry state and a rolling-horizon solve; project-status claims require GitHub release evidence; improvement questions require validation gaps and benchmark evidence. If the required artifact is absent, report the gap.

Every answer uses exactly four sections: production result, current evidence, unresolved risks, and proposed model improvement. Never invent or manually adjust a squad. Correct the input or model layer, rerun the same snapshot, and measure the change.

`safe_to_act` must be false for stale/mismatched snapshots, unhealthy or stale required sources, incomplete all-player truth coverage, missing required AIrsenal player/Gameweek coverage, invalid set-piece provenance, missing CVaR/regret/solver parity, incomplete optimisation, missing strategy state, or final selected-player evidence that does not match the actual canonical 15.

## EV-first evidence policy

The production eligibility rule is **adverse-evidence-only pre-solve**.

Expected minutes, start probability, appearance probability, role uncertainty and their confidence are already inputs to expected FPL points. They must not be turned into a second hidden safety preference that systematically rewards secure minutes over higher expected points.

A player may be removed from XI/captain eligibility only when current attributable evidence justifies it, including:

- official adverse availability/suspension status;
- decision-grade negative role/availability evidence;
- a current unresolved contradiction between supported positive and negative evidence.

Low numerical confidence by itself is diagnostic, not an exclusion rule. A high-uncertainty starter may therefore remain selectable when the forecast already prices that uncertainty. This is deliberate and prevents a return to the old minutes-conservative bias.

Feed health alone is not player evidence. Current tactical, availability or set-piece overrides require source name, source tier, URL, publication time and explicit expiry where relevant. Stale or unverifiable overrides are rejected before projection. Ordinal Official FPL set-piece order is factual hierarchy only and may not be converted into an invented literal future share.

## All-player truth requirement

The factual contract applies to **every current Official FPL player**, not only the selected 15.

Production requires:

- 100% Official FPL identity/name/club/position/price/status coverage;
- unique official IDs;
- 100% FPL Core player-ID coverage for the required enrichment source;
- 100% canonical player/Gameweek projection-pair coverage;
- 100% required AIrsenal player/Gameweek xP coverage;
- explicit fact/override/inference/forecast classification for decision-sensitive fields;
- no unsourced literal set-piece shares or unexplained set-piece xP.

Future minutes, lineups, roles and xP cannot be guaranteed with literal 100% certainty. They remain forecasts with transparent evidence/confidence instead of being disguised as facts.

## Completion standard

Completion means all five are present: GitHub commit, PR, passing CI, reproducible evidence artifact, and merged production output when activation is claimed. A local experiment is never a completed release.

## If the user asks for “the best team”

1. Do **not** compare several standalone Apex approaches and make a fresh subjective choice.
2. Load `data/generated/apex_answer_context.json` only.
3. If `safe_to_act` is false, report the blockers and do not invent a team.
4. If `safe_to_act` is true, present `production_result` as **the** Apex team.
5. Report XI, captain, vice and bench order from the final canonical contract.
6. Explain players using the final selector and `final_selected_player_evidence`.
7. Pinnacle exact-horizon, Elite, CVaR, regret and parity are internal diagnostics only; they cannot be described as competing recommendations or as the causal selector when they were not.
8. Show Haaland/no-Haaland or another forced alternative only when explicitly requested, and label it as a scenario rather than a competing recommendation.

## Canonical command

The production command is:

```bash
python scripts/run_apex.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
```

This is the only production entrypoint. It executes one-way:

1. seal the decision bundle;
2. run Pinnacle/Elite diagnostics;
3. assemble a non-actionable staging packet;
4. run all-player truth;
5. apply exactly one final adaptive/receding strategy selector;
6. exact-rescore the current Gameweek;
7. rebuild evidence for the actual final 15/XI/captain;
8. build the final answer context;
9. set `ready_to_act=true` only if every gate passes.

The only user-facing files are:

- `data/generated/apex_answer_context.json`
- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`

`pinnacle_latest.*` and `elite_latest.*` are internal diagnostics only.

Validate or replay the sealed surface with:

```bash
python scripts/audit_decision_bundle.py data/generated/decision_bundle
python scripts/replay_decision_bundle.py data/generated/decision_bundle
```

## Final strategy policy

Before GW1, the only canonical selector is `adaptive_gw1_launch_with_transfer_option_value`: exact GW1 expected points first, with future legal transfer option value used only inside the configured near-equivalent GW1 band.

Once a published current team exists, the only canonical selector is `receding_horizon_current_team_maximum_ev`: solve from the actual permanent squad, bank, selling prices and free-transfer state; publish only the first newly solved action; treat every later move as a contingency.

The static exact-horizon object remains a diagnostic compatibility surface only. It can never set `ready_to_act=true`.

## If the user shows a current team

Treat the screenshot/manual team as the current private draft if it is newer than the public FPL snapshot. Compare it against the canonical recommendation; do not replace the canonical selection policy with an ad-hoc manual selector.

## If the user asks about project status

Check GitHub/repository state directly. Separate:

- **Production now** — merged/running/current canonical outputs.
- **In progress** — open PRs/experiments.
- **Proposed** — ideas not implemented.

Never describe a proposal as already part of production.

## If changing the model

- Preserve canonical `xp` unless the change is explicitly a forecast-model change.
- Keep observed facts, forecasts and selection logic separate.
- Add tests.
- Benchmark against the current baseline.
- Record the decision and reason.
- Use a branch/PR for non-trivial changes.
- Do not merge solely because CI is green; verify modelling intent and decision impact.
- Do not introduce a second user-facing team-selection path.
- Do not hand-tune a named player's weight/role to force a preferred squad.
- Do not promote a projection expert or change ensemble weights without bounded predictive evidence.

## Architecture freeze after PR #64

PR #64 is intended to be the final architecture/hardening pass for the launch decision engine. Once it is merged and the fresh production acceptance is green, normal Apex operation is **not** another architecture-PR cycle.

Routine operation becomes:

- refresh Official FPL and required sources;
- refresh current-season match/player evidence;
- update forecasts using already approved rules;
- ingest current injuries/roles/lineups with provenance;
- re-solve before each deadline;
- archive forecast/decision/outcome data for no-hindsight learning.

Architecture/model work reopens only when one of these is true:

1. a reproducible production defect violates the frozen contract;
2. a required upstream changes schema/semantics and the engine cannot reconcile it safely;
3. a bounded challenger demonstrates superior predictive and decision-level validity under the established promotion gates.

A surprising player or a poor one-week outcome is **not** sufficient reason to redesign the engine. Diagnose the input, truth, forecast and decision layers first.

## Communication standard

Prefer concise, decisive outputs. State uncertainty where it changes action. Avoid repeatedly asking the user for information already stored in repository/project context.

## Anti-drift rules

Do not:

- start from generic web lists;
- optimise only points-per-million;
- force premium players because of reputation;
- force cheap picks because of value;
- use ownership in the pure maximum-points objective;
- present Pinnacle, exact-horizon, Elite, CVaR or Value as separate Apex recommendations;
- claim a “9.9/10” score without defining what the score means;
- confuse model confidence with probability of winning;
- claim a PR is green without checking the actual workflow run;
- tell the user to run commands when the connected repository can answer the question directly;
- turn an ordinal rank into an invented probability;
- let a required expert silently disappear for only some players and renormalise weights without a blocker.

## Documentation maintenance

After a meaningful architecture/model milestone update:

- `CURRENT_STATE.md`
- `SESSION_LOG.md`
- `APEX_CHANGELOG.md`
- `APEX_DECISIONS.md` if a durable decision changed
- `BENCHMARKS.md` if model performance/selection changed
- `KNOWN_ISSUES.md` if a limitation is discovered/resolved
- `APEX_CANONICAL_DECISION_POLICY.md` only if the single production decision contract itself changes
