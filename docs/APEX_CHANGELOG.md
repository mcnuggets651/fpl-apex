# Apex FPL — Changelog

This is a human project-level changelog. Git history remains the detailed code record.

## 2026-09-02 — Apex V2 runtime and authority reconciliation
- Reverified live `main`, frozen PR #90 and the prospective Decision Quality failure before changing anything.
- PR #114 corrected the independent Decision Quality solve-task timeout from 30 to 50 minutes without changing the frozen engine, horizon, candidate depth, MIP precision or exact mechanics.
- Added a frozen-source regression that derives the 34-minute theoretical MILP allowance and requires explicit orchestration headroom.
- Introduced `docs/APEX_V2_AUTHORITY.json` as the machine-readable production constitution and rebuilt generic governance around the frozen V2 config.
- Rewrote the canonical Project Brain surfaces so immutable Apex V2 Daily Production and AIrsenal H1–H8 are the only serving authority.
- Archived the retired `pinnacle.yml`, `airsenal.yml`, `refresh-core-pin.yml` and `gw1-final-2026.yml` publishers outside `.github/workflows` while preserving their forensic YAML.
- Extended the Apex V2 Ops Contract to guard the authority/docs/archive surface and reject restoration of obsolete executable publishers.

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
- Local validation: 174 tests, Ruff, governance, upstream pins and workflow YAML all pass. This remains an unmerged release candidate until PR/CI/production verification completes.

## 2026-08-08 — Project Brain v1
- Added canonical project context, decisions, architecture, model spec, data-source map, operating manual, roadmap, charter, current-state record, benchmarks, known issues, vision and session log.
- Established mandatory continuity/startup protocol for future Apex work.

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
