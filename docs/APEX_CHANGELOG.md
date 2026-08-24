# Apex FPL — Changelog

This is a human project-level changelog. Git history remains the detailed code record.

## 2026-08-24 — V2 Slice 10 independent decision assurance
- Added a dependency-free reference mechanics checker that independently reconstructs current-state legality, transfer resources, hits, squad/XI/bench/captain structure and expected mechanics without importing the DecisionEngine or its mechanics implementation.
- Added a deliberately different exhaustive realised-appearance-state autosub algorithm so independent mechanics evidence can detect shared implementation defects rather than simply repeat Slice 8 calculations.
- Added typed immutable reference-mechanics, external reference-solver and combined independent-assurance certificates with content-addressed offline replay and strict source-artifact verification.
- Added fail-closed external solver semantics: missing, limited, errored or merely feasible evidence remains INCONCLUSIVE; contradictory infeasibility, exact-objective disagreement or same-tie-policy action disagreement fails.
- Added a qualified reference-solver worker registry with no fabricated production champion; publication-grade solver parity requires an artifact-verified, season/horizon-valid qualified champion worker.
- Wired independent mechanics and reference-solver parity into the constitutional AssuranceCase as separate release-blocking proof obligations.
- Added architecture guards prohibiting DecisionEngine/production-mechanics, V1 optimiser/services, network clients, runtime RNG and scientific dataframe stacks from the independent assurance path.

## 2026-08-24 — V2 Slice 9 sealed scenario convergence
- Replaced legacy scenario/CVaR authority with dependency-free constitutional joint-scenario contracts and immutable `ScenarioSet` / `RobustnessReport` identities.
- Required external worker-produced joint streams with explicit generator, RNG, seed, ordering, weights, player/Gameweek outcomes and retained source artifacts; runtime RNG and inference of correlation from marginal forecast labels are prohibited.
- Added common-random-number nested-prefix convergence, exact weighted mean/lower-CVaR/tail metrics and player/Gameweek reconciliation to canonical Forecast xP.
- Added exact realized submitted-action scoring for captain/vice fallback, autosubs, chips and hits without scenario-specific hindsight optimization.
- Kept expected value as the anchor and constrained any converged robustness preference to an explicit EV-regret band; inconclusive reports expose no preferred action.
- Added fail-closed generator/policy registry with no fabricated production champions, strict offline replay and architecture/proof/requirements traceability.
- The historical 256-scenario count is now explicitly a minimum floor rather than a convergence certificate.

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
