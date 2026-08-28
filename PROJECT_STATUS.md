# Apex FPL — Project Status

**Audited:** 28 August 2026  
**Repository:** `mcnuggets651/fpl-apex`  
**Production branch at audit start:** `main` @ `80b31eede7d44b7412261aa8c9df994a4612a348`  
**Cleanup/cutover branch:** `agent/final-airsenal-authority-cutover`

## Current status

Apex is in a controlled production-authority cutover. The previous production configuration on `main` still uses the obsolete hand-set forecast blend and incorrectly allows stale FPL Core enrichment to block the entire decision. That state is fail-closed (`ready_to_act=false`, `safe_to_act=false`) and has **no current recommendation**.

The replacement architecture has been implemented and certified on the cutover branch:

1. **Official FPL — factual authority** for player ID, club, position, price, availability, fixtures and rules/mechanics inputs.
2. **AIrsenal — canonical statistical xP authority.** Production `xp` equals validated AIrsenal xP directly. Missing/stale AIrsenal coverage blocks; there is no silent Apex fallback.
3. **Apex proprietary projection — shadow only** until genuine prospective evidence earns promotion.
4. **FPL Core and Understat — enrichment/shadow inputs.** Their health remains visible and their data remains useful, but they are not canonical-xP dependencies.
5. **Apex optimiser — decision authority** for legal squad/transfer selection, exact FPL mechanics, captain/vice, bench/autosubs, robustness diagnostics and receding-horizon action selection.
6. **Prospective calibration — promotion authority.** No expert, blend or challenger may gain production forecast weight through subjective tuning.

The cutover implementation passed **127/127 authority/dependency regressions** and **384/384 full repository tests** in GitHub Actions, including the one-hot AIrsenal authority audit and the repaired publication import path.

## Current production artifacts

The latest tracked `apex_answer_context.json` / `apex_recommendation_latest.json` are intentionally non-actionable. They were generated on 28 August 2026 before this cutover and report `recommendation=null`.

Do not resurrect an earlier GW1 team, Pinnacle squad, chat-memory squad or historical `apex_latest` file. The only user-facing answer contract is:

- `data/generated/apex_answer_context.json`
- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`

A team may be shown only when the current context says `safe_to_act=true` and `ready_to_act=true`.

## Data audit

- Official FPL latest audited snapshot: `20260828T021354Z-463aea4b`; 616 players and 380 fixtures.
- Tracked AIrsenal projection file was generated `2026-08-26T06:01:52.744602+00:00`, source revision `8c7e18eba1488dd5a7d4bdb00d4da0a75e895717`; it must be refreshed before final production execution.
- FPL Core candidate `b38c871765cb963223cbf471b28e65c4d58e9b64` was fully validated on 28 August: 616/616 Official player-ID coverage, no identity mismatches, upstream checks green. The old refresh workflow failed only because the Apex package was not installed before publication invalidation.
- FPL Core upstream later advanced again; no newer revision is accepted until the same semantic validation runs successfully.
- Calibration archive currently contains 0 completed genuine prospective Gameweeks / 0 active rows. No projection promotion is authorized.

## Cleanup completed in this branch

- retired the temporary final-cutover workflow after it completed its job;
- archived and removed the expired one-off `gw1-final-2026.yml` workflow;
- repaired FPL Core refresh packaging/import behavior without weakening validation or publication invalidation;
- changed production xP authority to AIrsenal-only and retained Apex as shadow;
- changed Core/Understat/fixture enrichments from false hard dependencies to explicit optional-enrichment health;
- added prospective provider-ledger support so production and shadow forecasts can be frozen and compared later;
- removed stale fixed production-blend literals from active config/tests;
- replaced obsolete pre-GW1 current-state documentation.

## Remaining before final production execution

1. Merge the audited cleanup/cutover to `main` after branch CI/governance is green.
2. Run the repaired FPL Core refresh to validate and publish the latest enrichment pin.
3. Refresh AIrsenal from its pinned worker and verify complete current horizon coverage.
4. Run Apex Unified on the merged SHA with a fresh Official FPL snapshot.
5. Inspect the sealed DecisionBundle, solver parity, all-player truth, evidence, exact mechanics and answer context.
6. Publish a team only if the final contract is genuinely actionable.
7. Repair the missing genuine deadline-learning archive path before relying on post-GW1 calibration.

## V2 stack

Draft PRs #67–#88 are a separate stacked V2 architecture programme and remain **withheld**. They contain valuable certified mechanisms, but their latest documentation still assumes the old 51.11% Apex / 26.67% Official EP / 22.22% AIrsenal forecast blend. They must be rebased/requalified against the new AIrsenal-only production authority before any future merge. They are not current production truth.

PR #66 is superseded V1 archaeology/regression material and must not be merged.

## Operating rule

For all future project work, use [`docs/APEX_OPERATING_MANUAL.md`](docs/APEX_OPERATING_MANUAL.md) and [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md). Repository artifacts and current workflow evidence outrank conversation memory.
