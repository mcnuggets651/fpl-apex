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
5. Inspect `data/generated/apex_answer_context.json`. It is the only permitted
   input for an Apex-labelled answer.
6. Verify `safe_to_act`, run age, snapshot hashes, source health, model versions,
   CVaR, selection regret, solver parity, role/news evidence and strategy state.
7. Only inspect internal diagnostics to explain a blocker or improve the engine.
8. Use live research only as a labelled gap-fill for injuries, transfers, roles
   and lineups; it cannot silently override the canonical contract.
9. If code/architecture is changing, read the relevant model/architecture docs and current implementation.

## Closed-answer contract

Every substantive FPL question is routed before answering. Best-team questions
require the canonical strategy; player-role questions require a player evidence
dossier; player comparisons require one matched snapshot plus objective regret;
transfers require current entry state and a rolling-horizon solve; project-status
claims require GitHub release evidence; improvement questions require validation
gaps and benchmark evidence. If the required artifact is absent, report the gap.

Every answer uses exactly four sections: production result, current evidence,
unresolved risks, and proposed model improvement. Never invent or manually adjust
a squad. Correct the input or model layer, rerun the same snapshot, and measure the
change.

`safe_to_act` must be false for stale/mismatched snapshots, unhealthy or stale
required sources, missing CVaR/regret/solver parity, insufficient selected-player
minutes/role provenance, incomplete optimisation, or missing strategy state.

Completion means all five are present: GitHub commit, PR, passing CI,
reproducible evidence artifact, and merged production output when activation is
claimed. A local experiment is never a completed release.

## If the user asks for “the best team”
1. Do **not** compare several standalone Apex approaches and make a fresh subjective choice.
2. Load `data/generated/apex_recommendation_latest.json`.
3. If `ready_to_act` is false, report the blockers and do not invent a team.
4. If `ready_to_act` is true, present `recommendation` as **the** Apex team.
5. Report XI, captain, vice and bench order from the canonical contract.
6. Use epsilon/Pinnacle/CVaR/regret evidence only to explain confidence or fragility.
7. Show Haaland/no-Haaland or another alternative only when explicitly requested, and label it as a scenario rather than a competing recommendation.

## Canonical command
The production command is:

```bash
python scripts/run_apex.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
```

This command produces the only user-facing files:
- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`

`pinnacle_latest.*` and `elite_latest.*` are internal diagnostics only.

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
- Keep selection logic separate from forecast construction.
- Add tests.
- Benchmark against the current baseline.
- Record the decision and reason.
- Use a branch/PR for non-trivial changes.
- Do not merge solely because CI is green; verify modelling intent and benchmark effects.
- Do not introduce a second user-facing team-selection path.

## Communication standard
Prefer concise, decisive outputs. State uncertainty where it changes action. Avoid repeatedly asking the user for information already stored in repository/project context.

## Anti-drift rules
Do not:
- start from generic web lists;
- optimise only points-per-million;
- force premium players because of reputation;
- force cheap picks because of value;
- use ownership in the pure maximum-points objective;
- present Pinnacle, Elite, CVaR or Value as separate Apex recommendations;
- claim a “9.9/10” score without defining what the score means;
- confuse model confidence with probability of winning;
- claim a PR is green without checking the actual workflow run;
- tell the user to run commands when the connected repository can answer the question directly.

## Documentation maintenance
After a meaningful architecture/model milestone update:
- `CURRENT_STATE.md`
- `SESSION_LOG.md`
- `APEX_CHANGELOG.md`
- `APEX_DECISIONS.md` if a durable decision changed
- `BENCHMARKS.md` if model performance/selection changed
- `KNOWN_ISSUES.md` if a limitation is discovered/resolved
- `APEX_CANONICAL_DECISION_POLICY.md` only if the single production decision contract itself changes
