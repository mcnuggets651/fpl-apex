# Apex FPL — Current State

**Last updated:** 2026-08-11

## Production

- Repository: `mcnuggets651/fpl-apex`
- Production branch: `main`
- Production selector: canonical xP → legal maximum-EV optimiser → correlated
  robustness/Elite diagnostics → maximum-EV fallback when the Elite frontier is
  unstable → exact Gameweek mechanics → one published recommendation.
- PR #16 is merged. The Understat team-strength challenger is shadow-only and
  does not change canonical publication.
- PR #14 is closed and superseded. It combined model activation, readiness
  semantics and uncalibrated captain telemetry, and its original historical
  validator used an outcome-selected prediction cohort.
- PR #17 is merged. It fixes versioned season rules/free transfers and adds the
  deterministic replay foundations.
- PR #18 is merged. It adds a dormant attack-only shrinkage candidate and the
  corrected shadow validator; it does not connect shrinkage to production.

The only production command is:

```bash
python scripts/run_apex.py --horizon 8 --stochastic-scenarios 256 --cvar-alpha 0.10 --cvar-weight 0.20 --force
```

The only user-facing outputs are:

- `data/generated/apex_recommendation_latest.json`
- `data/generated/apex_recommendation_latest.md`

## ChatGPT query discipline

Every FPL/player/squad/transfer question must follow
[`CHATGPT_APEX_QUERY_POLICY.md`](CHATGPT_APEX_QUERY_POLICY.md).

In particular: load this Project Brain and the latest canonical recommendation
before answering; use committed Apex and pinned-upstream evidence first; do not
browse externally unless a concrete repository evidence gap prevents a defensible
answer; and never mix production, shadow, open-PR or stale artifacts without
labelling the distinction.

## Latest verified canonical recommendation

The post-PR #17 publication at 2026-08-09 11:36 UTC is decision-ready:

- selector: **maximum_ev**
- reason: the Elite epsilon frontier did not converge
- horizon objective: **319.5816697527 raw xP**
- GW1 exact-mechanics total: **51.5251454610 xP**
- captain: **Haaland**
- vice-captain: **B.Fernandes**
- official bootstrap SHA-256 prefix: `1b658fa96da5`
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

The Understat challenger from PR #16 is merged in shadow mode. Its component
checks passed and it does not alter canonical publication. The exact PR #17
merge SHA passed 142 local tests/Ruff, and the subsequent Apex Unified run
published the decision-ready artifact above.

### Player-rate shrinkage

A clean research implementation is merged from PR #18 with only:

- the dormant shrinkage model;
- production-parity cohort construction;
- corrected chronological validator and tests;
- durable validation evidence.

The corrected full-roster validator passes its xG90/xA90 chronological shadow
gate across 2024/25 and 2025/26, including pre-GW1, GW1-5 and GW6+ strata.
DEFCON fails and is a no-op by default. Those seasons have been inspected during
development, so they are not independent final holdouts. The merged report sets
`production_activation_authorized=false`; activation requires a separate PR and
decision.

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

1. Preserve PR #14 as closed/superseded and keep shrinkage dormant.
2. Build the remaining historical adapter, transfer/chip controller, isolated
   scorer and 38-GW orchestrator under `FULL_SEASON_REPLAY_PROTOCOL.md`.
3. Freeze code, policies and metrics before opening 2025/26 outcomes.
4. Run 2025/26 as the locked strategy/mechanics benchmark.
5. Preserve every 2026/27 pre-deadline bundle and decision for prospective
   validation.

## Current boundaries

- Public FPL cannot expose unpublished pre-deadline private transfers.
- Market odds remain optional until a validated feed is configured and healthy.
- New-season expected minutes and attacking rates remain prior-heavy.
- Elite epsilon and captain scenario coefficients are not calibrated.
- Full-season transfer/chip execution is not yet implemented.
