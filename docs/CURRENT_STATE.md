# Apex FPL — Current State

Operating authority: [`APEX_OPERATING_MANUAL.md`](APEX_OPERATING_MANUAL.md).

**Last audited:** 2026-08-28  
**Production `main` at audit start:** `80b31eede7d44b7412261aa8c9df994a4612a348`  
**Active cleanup/cutover branch:** `agent/final-airsenal-authority-cutover`

## Production now

The current `main` publication is fail-closed. The latest tracked answer context and recommendation contain `safe_to_act=false`, `ready_to_act=false` and `recommendation=null`. Do not use any older squad as a fallback.

The failed production state is understood: it combines an obsolete forecast-authority policy with a stale FPL Core enrichment pin. FPL Core itself was not broken; the validated refresh workflow failed at publication invalidation because the Apex package had not been installed in that job.

No current XI, captain, vice-captain or bench is authorized until the post-cutover Apex Unified run succeeds.

## Audited replacement authority

The cutover branch implements the following production dependency graph:

- **Official FPL — factual truth.** Exact current player IDs, clubs, FPL positions, prices, availability, fixtures and rules inputs.
- **AIrsenal — production statistical xP.** Canonical `xp` is the validated AIrsenal number exactly. Missing/stale/incomplete AIrsenal blocks production. There is no Apex fallback in production mode.
- **Apex proprietary xP — shadow.** Retained for diagnostics and prospective challenger evaluation only.
- **FPL Core — enrichment.** Retained for prior-season/current supporting statistics, preseason/Elo/DefCon and research. Staleness or unavailability is disclosed but is not a canonical-xP blocker while AIrsenal is independent of it.
- **Understat — enrichment/shadow.** Retained for underlying-stat priors, team/player research and shadow-model features. Empty/invalid payloads are unhealthy rather than accepted as valid zero data.
- **Football evidence — availability/minutes/role context.** Hard current evidence may exclude/invalidate; soft evidence affects uncertainty/scenarios rather than manufacturing xP bonuses.
- **Apex optimiser — decision authority.** Legal current-state optimisation, exact mechanics, XI/captain/vice/bench/autosubs and receding-horizon first-action selection.
- **Prospective calibration — promotion judge.** No automatic model or weight promotion.

The authority cutover passed 127 focused regressions and all 384 repository tests in GitHub Actions before source publication to the branch.

## Latest audited data facts

### Official FPL

Latest audited production snapshot:

- snapshot ID: `20260828T021354Z-463aea4b`
- bootstrap SHA-256: `b7824c11828ead43d315578233f03ff15a9ca51c8cd01c31f0a3b2b3b99a15c8`
- fixtures SHA-256: `ff77d62793e06a7b24c9789ca1be5722733483c7d0261728a3961f8bfa7da684`
- players: 616
- fixtures: 380

A final production solve must acquire a new Official snapshot rather than assuming this remains current.

### AIrsenal

The tracked forecast file was generated `2026-08-26T06:01:52.744602+00:00` from pinned revision `8c7e18eba1488dd5a7d4bdb00d4da0a75e895717`. The pre-cutover failed bundle contained 4,928 player/Gameweek AIrsenal rows, but the file must be refreshed before final execution.

### FPL Core

Workflow run `33133887512` validated candidate `b38c871765cb963223cbf471b28e65c4d58e9b64` with:

- 616 Official players;
- 616 unique Core player IDs;
- 100% Official player-ID coverage;
- 100% previous bridge coverage;
- no identity mismatch warnings;
- ~75.97% previous-minutes coverage;
- all governed upstream checks green after the candidate pin update.

The run failed only when `scripts/invalidate_published_decision.py` imported `apex_fpl`. The refresh workflow now installs the Apex package and verifies that import before validation/publication. A later Core upstream revision must still pass the same candidate-validation gate before being pinned.

### Prospective learning

`data/generated/calibration_report.json` currently records:

- completed genuine Gameweeks: 0
- rows: 0
- active rows: 0
- promotion: blocked for insufficient history

There is also no tracked `data/history/deadlines` archive on `main`. This is a genuine post-GW1 learning-operations gap to repair before any projection challenger can accumulate authoritative prospective evidence.

## Workflow surface

The one-off `gw1-final-2026.yml` workflow is expired and has been moved to `archive/workflows/`. The temporary cutover executor is removed after use.

Active production/acceptance workflows remain the normal recurring AIrsenal, Apex CI, Apex Unified, Core enrichment refresh, readiness and bounded audit surfaces. The governance checker owns the exact active/archived set.

## Open PRs

- **PR #66:** superseded V1 specialist branch; archaeology/regression only; do not merge.
- **PRs #67–#88:** stacked V2 programme. These remain draft/withheld. Their later heads still document the obsolete fixed three-way forecast blend, so they require rebase/requalification against the new authority contract before future merge.

Do not treat open-PR code as production truth.

## Immediate completion sequence

1. Finish branch cleanup and documentation consistency.
2. Run branch CI/governance on the final cleanup head.
3. Merge the cleanup/cutover to `main` only if green.
4. Run repaired FPL Core enrichment refresh on `main`.
5. Refresh AIrsenal and require complete fresh horizon coverage.
6. Run Apex Unified from a fresh Official FPL snapshot.
7. Inspect one sealed bundle/generation across optimiser, parity, exact mechanics and answer context.
8. Publish a recommendation only if `safe_to_act=true` and `ready_to_act=true`.
9. Repair/verify deadline forecast archiving so genuine prospective learning starts operating post-GW1.

## Non-negotiable boundaries

- Never reconstruct a team from chat memory or historical markdown.
- Never use remembered prices or identities over Official FPL.
- Never promote Apex proprietary xP because it looks plausible.
- Never silently substitute Apex when canonical AIrsenal is absent.
- Never turn Core/Understat enrichment health into a false production blocker when the canonical path is independent of it.
- Never weaken solver parity, identity, statistical truth, exact mechanics or freshness protections merely to obtain green CI.
