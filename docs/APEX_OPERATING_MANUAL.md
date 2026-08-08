# Apex FPL — Operating Manual

## Purpose
This file defines how ChatGPT or any operator should work on Apex without repeatedly reconstructing context.

## Mandatory startup sequence
For any substantive Apex request:
1. Read `docs/CURRENT_STATE.md`.
2. Read `docs/APEX_MASTER_CONTEXT.md`.
3. Read `docs/APEX_DECISIONS.md`.
4. Inspect the latest generated production outputs.
5. If code/architecture is changing, read the relevant model/architecture docs and current implementation.
6. Report the current state before proposing future state when the distinction matters.

## If the user asks for “the best team”
1. Load current Official FPL/source state; do not reuse a remembered squad.
2. Confirm readiness gates.
3. Read latest Pinnacle and Elite outputs.
4. Compare unrestricted, Haaland/no-Haaland or other relevant scenarios.
5. Compare raw xP, Elite utility, minutes/start security, captaincy, ceiling, DEFCON/bonus and exact regret.
6. Produce one final recommendation, not a chain of contradictory drafts.
7. Clearly label any override of the solver and quantify the cost/reason.

## If the user shows a current team
Treat the screenshot/manual team as the current private draft if it is newer than the public FPL snapshot. Compare it against generated candidates; do not assume the public API can see unpublished transfers.

## If the user asks about project status
Check GitHub/repository state directly. Separate:
- **Production now** — merged/running/current outputs.
- **In progress** — open PRs/experiments.
- **Proposed** — ideas not implemented.

Never describe a proposal as already part of production.

## If changing the model
- Preserve canonical `xp` unless the change is explicitly a forecast-model change.
- Add tests.
- Benchmark against the current baseline.
- Record the decision and reason.
- Use a branch/PR for non-trivial changes.
- Do not merge solely because CI is green; verify modelling intent and benchmark effects.

## Communication standard
Prefer concise, decisive outputs. State uncertainty where it changes action. Avoid repeatedly asking the user for information already stored in repository/project context.

## Anti-drift rules
Do not:
- start from generic web lists;
- optimise only points-per-million;
- force premium players because of reputation;
- force cheap picks because of value;
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
