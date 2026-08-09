# Apex FPL — Current State

**Last updated:** 2026-08-09

## Production

- Repository: `mcnuggets651/fpl-apex`
- Production branch: `main`
- Production selector: canonical xP → legal maximum-EV optimiser → correlated
  robustness/Elite diagnostics → maximum-EV fallback when the Elite frontier is
  unstable → exact Gameweek mechanics → one published recommendation.
- PR #16 is merged. The Understat team-strength challenger is shadow-only and
  does not change canonical publication.
- PR #14 is blocked and must not be merged as written. It combines model
  activation, readiness semantics and uncalibrated captain telemetry, and its
  original historical validator used an outcome-selected prediction cohort.
- PR #17 contains the versioned season-rule correction and deterministic replay
  foundations. It remains a draft until independent CI and review are green.

The only production command is:

```bash
python scripts/run_apex.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
```

The only user-facing outputs are:

- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`

## Latest verified canonical recommendation

The 2026-08-09 10:55 UTC publication on `main` is decision-ready:

- selector: **maximum_ev**
- reason: the Elite epsilon frontier did not converge
- horizon objective: **319.5816697527 raw xP**
- GW1 exact-mechanics total: **51.5251454610 xP**
- captain: **Haaland**
- vice-captain: **B.Fernandes**
- official bootstrap SHA-256 prefix: `1336496b32c3`
- fixtures SHA-256 prefix: `a478e20d030d`

Canonical 15:

- GK: Verbruggen, Petrović
- DEF: Virgil, Guéhi, Thiaw, Kayode, A.Murphy
- MID: B.Fernandes, Enzo, Schade, Ndiaye, Tavernier
- FWD: Haaland, Thiago, Neave

GW1 XI:

- Verbruggen
- Guéhi, Virgil, Thiaw, Kayode
- B.Fernandes, Enzo, Schade, Ndiaye
- Haaland, Thiago

Bench: Petrović; Tavernier → A.Murphy → Neave.

This remains the official **pre-shrinkage** baseline. No shadow challenger may
overwrite it.

## Model status

### Team strength

The Understat challenger from PR #16 is merged in shadow mode. Its PR checks
passed, but exact post-merge `main` CI was not independently evidenced during
the release audit. Run Apex CI and Apex Unified on the exact release SHA before
tagging.

### Player-rate shrinkage

A clean research PR must be cut from current `main` with only:

- the dormant shrinkage model;
- production-parity cohort construction;
- corrected chronological validator and tests;
- durable validation evidence.

Do not include pipeline activation or readiness-semantics changes. The 2024/25
and 2025/26 seasons have been inspected during development, so they are
chronological evaluation seasons, not untouched final holdouts. Production
activation requires a separately reviewed decision after corrected evidence.

### Captain uncertainty

The fixed-XI captain frequency is telemetry only. Scenario coefficients and the
proposed 50% threshold are not historically calibrated; the raw production
control also fails that threshold. Keep this diagnostic out of readiness until
coverage/discrimination have been calibrated.

## Full-season validation

The 2025/26 deadline archive is feasible and should be run as a locked
pseudo-prospective integration/strategy benchmark with a cutoff of
`deadline - 120 minutes`. It must include transfers, hits, chips, XI, bench
order, captaincy, autosubs, state reconciliation and isolated realised scoring.

It is not the final independent model validation because completed 2025/26
evidence influenced model design. Freeze the shipped code/configuration and use
the 2026/27 deadline archive as the true prospective final test.

## Immediate release sequence

1. Keep PR #14 blocked; supersede it with a clean dormant research PR.
2. Merge PR #17 only after its CI/review is green.
3. Run Apex CI and Apex Unified on the exact candidate release SHA.
4. Confirm the canonical artifact is decision-ready and reproducible.
5. Tag only that verified SHA.
6. Build the remaining historical adapter, transfer/chip controller, isolated
   scorer and 38-GW orchestrator under `FULL_SEASON_REPLAY_PROTOCOL.md`.
7. Freeze policies/metrics before opening 2025/26 outcomes.
8. Preserve every 2026/27 pre-deadline bundle and decision for prospective
   validation.

## Current boundaries

- Public FPL cannot expose unpublished pre-deadline private transfers.
- Market odds remain optional until a validated feed is configured and healthy.
- New-season expected minutes and attacking rates remain prior-heavy.
- Elite epsilon and captain scenario coefficients are not calibrated.
- Full-season transfer/chip execution is not yet implemented.
