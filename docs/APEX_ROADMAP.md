# Apex V2 — Roadmap

Machine authority: [`APEX_V2_AUTHORITY.json`](APEX_V2_AUTHORITY.json). Operating authority: [`APEX_OPERATING_MANUAL.md`](APEX_OPERATING_MANUAL.md).

Immutable forensic base (`frozen_engine_sha`): `99cc7b51b0cff45462b567084cb1844cfe0a456f`

Current serving core: read `production_core_sha` from `APEX_V2_AUTHORITY.json`.

The immutable base anchors PR #90/lineage and never moves during successor promotion. The sole serving workflow is `.github/workflows/apex-v2-daily-production.yml`, and **AIrsenal** is the sole serving provider H1–H8.

## Current release — certified serving core plus prospective evidence

The production architecture is stable, but serving code is now independently versioned through `production_core_sha`. `main` may improve bounded operations/governance/research without modifying serving semantics; serving-code changes require a separately certified immutable successor and deliberate pointer promotion.

Current priorities:

1. keep authenticated immutable V2 Daily Production healthy and fail-closed;
2. keep the serving-core certification/readiness path reproducible across runners;
3. complete prospective multi-provider evaluation without serving influence;
4. keep Project Brain, generic governance and executable workflow inventory aligned with machine authority;
5. improve forecast calibration and decision quality prospectively rather than through hindsight.

## Production foundations

- Official FPL factual authority and snapshot anchoring;
- exact authenticated manager state for entry 63984;
- immutable PR #90 forensic/base lineage at `99cc7b51b0cff45462b567084cb1844cfe0a456f`;
- independently governed serving code through `production_core_sha`;
- AIrsenal sole serving H1–H8 provider;
- immutable private prerequisites and final production releases;
- offline solve after one frozen input snapshot;
- exact XI/captain/vice/bench/transfer mechanics;
- fail-closed auth/data/provider/publication gates;
- exact serving-core provenance from intent through acquisition and final publication;
- deadline-aware production dispatch and bounded auth keepalive.

## Prospective research foundations

- Apex Proprietary shadow H1–H8;
- Dastan shadow H1 only;
- PITCHSIDE/OpenFPL diagnostic/shadow intake;
- no-hindsight immutable provider tournament;
- prospective online learning for forecast/minutes/start/appearance/role disagreement;
- prospective Decision Quality counterfactuals with exact realized FPL scoring;
- parallel/resumable immutable task staging;
- no blending, voting, automatic promotion or serving influence.

## Near-term work

### Portable reproducibility closure

Close the cross-runner deterministic-replay portability defect without weakening decision identity. Backend-only solver status/MIP-gap telemetry must not define FPL semantics, while recommendation, certification, optimiser policy/objectives, serving map and evidence remain replay-bound. Certified and operational readiness installs must use the serving core's exact lock when available.

### Prospective calibration

As completed Gameweeks accumulate, score xP error and minutes/appearance/start/60 calibration prospectively, preserve every predeadline forecast, and use the evidence to challenge rather than silently rewrite the serving champion.

### Reliability and observability

Add runtime/SLO evidence for acquisition, optimisation, publication and the deterministic initial-squad canonicalisation path. Fault injection should prove fail-closed behavior for provider staleness, incomplete evidence, storage/release failures and provenance disagreement.

### External provider intake governance

Do not automate permission-restricted/unverified providers until the required licence/automation permissions are confirmed and a governed non-serving intake contract exists.

## Longer-horizon research

Potential improvements must remain challengers until prospectively validated:

- calibrated Bayesian minutes/start/appearance models;
- fixture-model experts such as Dixon-Coles/Poisson;
- richer penalty/set-piece share inference;
- DEFCON/BPS probability models;
- calibrated match/fixture simulations and covariance;
- chip opportunity-cost modelling;
- ownership/rank-game-theory research when the objective explicitly requires it.

None of these belongs in serving production merely because it is theoretically attractive. A serving change requires explicit architecture review, no-hindsight evidence, re-certification and a deliberate `production_core_sha` migration while `frozen_engine_sha` remains unchanged.

## Definition of “Apex 10.0”

Not perfect foresight. It means one coherent, reproducible and auditable production authority: exact state, current facts, qualified serving projections, legal maximum-EV optimisation, exact FPL mechanics, immutable publication, prospective learning and governance that fails when architecture descriptions or serving-core identity drift.
