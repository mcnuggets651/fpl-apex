# Apex V2 Production Architecture

## Status
Frozen architecture. Implementation must change this document and the acceptance tests together; code is not allowed to silently redefine the contract.

## Authority hierarchy
1. Official FPL is the sole authority for element identity, club, position, price, availability/status fields, fixtures and deadlines.
2. Forecast providers predict points only. They never redefine Official facts.
3. A single explicitly authorized serving provider is selected independently for each supported horizon. A shadow can never serve.
4. The decision engine consumes only `ProductionProjectionSurface`; shadow/disagreement/tournament diagnostics are not representable in its input type.
5. Hard evidence may exclude a player only when it has verifiable Official-club/Official-league provenance, timestamps and expiry. Soft news is audit/shadow evidence until prospectively qualified.
6. Exact FPL legality and cash/FT mechanics are provider-blind.
7. One certification surface decides whether a result is actionable.

## Why there is no production ensemble yet
A blend is not intrinsically safer than a single forecast. Without identical pre-deadline rows, synchronized scoring rules and chronological holdouts, a weight is an opinion expressed as a decimal. Apex V2 therefore starts with AIrsenal as the explicitly authorized operational incumbent, while Dastan and OpenFPL remain first-class challengers. Dastan/OpenFPL can become serving candidates only after a current-season-compatible live exporter passes the same operational contract.

The research tournament may evaluate non-negative simplex weights, but it is incapable of changing `serve_authorized`. Production weighting remains exactly 100% to the selected serving provider until a separate governed promotion is approved.

## Prospective tournament
Every deadline freezes every available provider before kickoff. Evaluation uses player-gameweek grain and same-row comparisons. Minimum promotion evidence is 8 genuine pre-deadline GWs; 12+ is preferred. Measurements include RMSE, MAE, bias, within-GW Spearman, NDCG@10/25, starter-only cohorts, availability/minutes where supplied, return bands, captain candidates and eventually end-to-end system-decision points. Historical fitting may generate hypotheses but cannot replace prospective evidence.

Any future ensemble must:
- use non-negative weights summing to one;
- train only on forecasts frozen before their deadlines;
- use chronological train/validation/test splits;
- beat the best constituent on held-out decision quality, not merely pooled MAE;
- avoid material cohort regressions;
- survive bootstrap/leave-GW-out sensitivity;
- receive an explicit governance release before production authority changes.

No automatic promotion is implemented.

## OpenFPL adaptation boundary
OpenFPL has three independent gates. Passing a later-sounding engineering step never implies passing the next governance step.

1. **Reference reproducibility.** Apex pins the exact upstream OpenFPL commit, runtime dependencies, five cross-validation folds, five position groups, feature/scaler artifacts and median-ensemble reference logic. Passing this gate proves only that the historical reference implementation is intact.
2. **Current-training readiness.** The published reference was developed on old FPL scoring seasons and uses score-dependent historical feature families including FPL points, BPS and bonus over 1/3/5/10/38-match windows. Legacy weights or old feature rows therefore cannot be relabelled `fpl-2026-27-v1`. Apex separately pins exact 2026/27 history and records the completed pre-target gameweeks. No minimum training sample is invented in code: a governed training-policy version must explicitly set that minimum. A current model artifact must bind to that policy, declare the exact-rule gameweeks used, train strictly before the target GW, use separately hashed training/model artifacts, prove future-placeholder invariance and reach 100% Official DecisionUniverse forecast coverage.
3. **Prospective serving promotion.** Even a valid current-rules OpenFPL model remains `SHADOW`, `serve_authorized=false` and prospectively unqualified. It must then accumulate genuine pre-deadline forecasts and pass the same tournament/promotion governance as every other challenger before production authority can change.

Current-rule training readiness is not a shortcut around the prospective tournament, and prospective accuracy can never retroactively validate a leakage-prone or incorrectly labelled training artifact.

## Run lifecycle
1. Publish immutable attempt **intent**.
2. Acquire all candidate provider outputs and external evidence.
3. Fetch Official FPL again as the final factual anchor.
4. Validate provider identity/coverage/freshness against that anchor.
5. Freeze one content-addressed local snapshot. Acquisition is now closed.
6. Solve from frozen files only. `runtime/solve.py` cannot import source/network modules and the architecture linter enforces this.
7. Certify once.
8. Publish the completed attempt as a GitHub **immutable release**, whether actionable or blocked.
9. After the GW finishes, publish immutable outcome and evaluation releases.
10. Detect an intent without a final release after the grace period as an operational incident.

## Persistence
Git commits are source code, not production state. Production forecasts/decisions/outcomes use GitHub Releases. Repository-level **Release immutability must be enabled before cutover**. Releases are built as drafts, assets are attached, then the release is published. Once GitHub immutability is enabled, its tag and assets are locked and GitHub supplies a release attestation.

Apex also stores SHA-256 manifests inside each bundle. This is defense in depth, not a substitute for GitHub's native immutability.

## Decision semantics
The primary objective is expected submitted FPL points plus captain copy, minus exact transfer hits. Free transfers are not assigned artificial point values. If two transfer plans are equal within numerical tolerance, a second optimization pass minimizes transfer count. Thus flexibility is a tie-break unless evidence demonstrates a measurable EV value.

If only H1 is qualified, discretionary transfers are withheld. The engine still optimizes the submitted XI/captain/bench for the current squad. It does not invent future xP.

If exact selling-price state is unavailable, discretionary transfer optimization is withheld. The engine does not assume current market price equals sale value.

When the serving provider supplies no appearance probabilities, contingent autosub and captain-no-show fallback value are not invented. The decision remains legal and uses unconditional provider xP; certification is degraded with an explicit warning.

## Failure domains
- Official truth failure: blocking.
- Serving forecast stale/incomplete: blocking unless an explicitly authorized standby independently qualifies.
- Shadow/challenger failure: warning only.
- Optional enrichment failure: warning only.
- Illegal squad/XI/cash state: blocking.
- Missing final release after intent: operational failure.
- Snapshot hash mutation: blocking integrity violation.

## Legacy boundary
`src/apex` may never import `src/apex_fpl`. V1 remains live only during migration. After a real V2 pre-deadline lifecycle passes the cutover gate, legacy production workflows and canonical generated-state writers are archived/deleted in the cutover PR.
