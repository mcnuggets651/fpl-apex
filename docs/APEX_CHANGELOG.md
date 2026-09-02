# Apex FPL — Changelog

This is a human project-level changelog. Git history remains the detailed code record.

## 2026-09-02 — Apex V2 acceptance and operations closure
- Completed live GW3 Decision Quality acceptance on corrected run `33643925982`: all 8/8 deterministic fresh tasks sealed before the deadline, exact production-baseline reproduction passed, canonical assembly succeeded and immutable private lab `apex-v2/private-decision-lab/2026-2027/33590896695-1` was created.
- Confirmed the decision lab remains strictly non-serving (`production_influence = NONE`, `serving_authorized = false`) and that postoutcome correctly made no learning/serving change before GW3 outcomes existed.
- Closed the Project Brain/generic-governance drift through PR #115 and the post-merge documentation race through PR #116 while keeping frozen engine PR #90 open/draft/unmerged at `99cc7b51b0cff45462b567084cb1844cfe0a456f`.
- Audited the OpenFPL moving-history observer: it resolves the current-season ref to a full immutable commit SHA before reading rows, records that SHA/digest, and therefore does not require replacement with a stale fixed baseline.
- Migrated every executable GitHub workflow from deprecated mutable Node-20-era action majors to exact commit pins for Node-24-native `actions/checkout` v7.0.1, `actions/setup-python` v7.0.0, `actions/cache` v6.1.0 and `actions/upload-artifact` v7.0.1.
- Added `ops_tests/test_github_actions_runtime_contract.py` to reject stale/mutable GitHub-owned action references and pin drift.
- Added weekly GitHub Actions Dependabot updates so future runtime changes arrive through the repository's protected PR/check path.
- Tightened the V2 Ops Contract so the complete executable workflow set is an explicit operations surface while `archive/workflows/**` is immutable forensic history.
- Post-merge smoke testing separated authentication health from direct-credential diagnostics: managed Auth Keepalive successfully rotated/persisted owner refresh state while the static direct-owner token was rejected as expired. The incident-only Direct Auth Diagnostic is therefore manual `workflow_dispatch` only, with an operations regression prohibiting automatic push/schedule/workflow-run triggers and any serving/write authority.
- No frozen engine source/config, forecast model, provider authority, optimiser semantics or serving policy changed.

## 2026-08-11 — Decision-grade evidence ingestion candidate
- Added structured official-article publication/body extraction and bounded same-host
  HTTPS hydration for official HTML news indexes.
- Added ambiguity-safe player resolution using full names and official-club context.
- Added typed lineup, availability, tactical-role and set-piece evidence with
  event-specific expiry windows and local negation protection.
- Required official evidence or two independent trusted-media sources for captains
  and high-uncertainty starters; the readiness floor was not weakened.
- The current live audit remains honestly blocked: all three configured sources
  responded, but no current item was decision-relevant. PR 6 improves the path by
  which deadline evidence can qualify; it does not fabricate pre-press-conference coverage.

## 2026-08-11 — Projection calibration and ablation contract
- Added strict no-hindsight deadline validation, cohort and interval diagnostics,
  expanding-window holdouts, Gameweek-block bootstrap and refitted source ablations.
- Kept production ensemble weights frozen because no completed 2026/27 deadline
  outcomes exist; any future promotion remains a separate reviewed change.

## 2026-08-11 — Correctness and diagnostic-contract repair candidate
- Preserved missing preseason xG/xA/defensive returns through projection and tactical inference.
- Aligned CVaR and independent-parity captain fields with their real producer schemas.
- Added actual additions/removals to every constrained-regret result.
- Added MILP incumbent, bound, achieved gap, node count and termination reason.
- Replaced the unused bench-weight list with one explicitly wired temporary approximation.
- Required the same sealed bundle ID in the answer contract and preserved one atomic workflow artifact before runtime cleanup.
- Local validation: 180 tests and Ruff pass; production publication remains gated on PR review, CI and a complete AIrsenal-backed run.

## 2026-08-11 — Sealed decision surface release candidate
- Added the content-addressed `apex-decision-bundle-v1` contract.
- Production ingestion/projection now runs once before Pinnacle and Elite.
- Added hashes for every material evidence and projection surface, upstream/code/config lineage, tamper checks and credential redaction.
- Added offline lineage audit/replay commands and retained bundles as workflow artifacts.
- Canonical and solver-parity gates now reject mismatched bundle identities.
- Local validation: 174 tests, Ruff, governance, upstream pins and all workflow YAML files pass. This remains an unmerged release candidate until PR/CI/production verification completes.

## 2026-08-08 — Project Brain v1
- Added canonical project context, decisions, architecture, model spec, data-source map, operating manual, roadmap, charter, current-state record, benchmarks, known issues, vision and session log.
- Established mandatory continuity/startup protocol for future Apex work.
- Recorded current Pinnacle/Elite relationship.
- Recorded Elite 10.0 weighting and safeguards.
- Separated production, validation-needed and proposed states.
- Added benchmark, known-issues and vision registers.

## 2026-08-07 — Elite 10.0
- Added Elite decision utility above Pinnacle's canonical xP surface.
- Initial weighting: 35% attack, 20% minutes, 15% captaincy, 10% set pieces/penalties, 10% fixture, 5% bonus/DEFCON, 5% value.
- Added raw-xP re-scoring/regret safeguard.
- Added unrestricted, Haaland and no-Haaland Elite scenarios.
- PR #6 passed the configured `Apex FPL` GitHub Actions workflow and was merged to `main`.

## Pinnacle era
- Established maximum-EV full-horizon optimisation.
- Added stochastic/CVaR robustness, exact selection regret, captain/vice/autosub mechanics and independent solver parity.
- Added personal entry synchronisation and receding-horizon transfer planning.
- Added no-hindsight deadline archive and calibration reporting.

## Foundation era
- Established Official FPL as canonical source.
- Integrated FPL Core Insights and genuine pinned AIrsenal.
- Built Apex projection decomposition, fixture/strength and tactical/news layers.
