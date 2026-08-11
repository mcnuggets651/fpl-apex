# Apex FPL — Changelog

This is a human project-level changelog. Git history remains the detailed code record.

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
