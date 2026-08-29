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
OpenFPL has four independent layers. Passing one never implies passing the next.

1. **Pinned reference inference reproducibility.** Apex pins the exact upstream OpenFPL commit, runtime dependencies, five cross-validation folds, five position groups, feature/scaler artifacts, sample schema and median-ensemble inference logic. The pinned repository publishes trained models, `data/samples.csv` and `play.ipynb`, and its README instructs users to construct custom samples themselves. It does not publish the executable sample-construction or model-training pipeline. The exact upstream identity is therefore `openfpl-reference-inference`, and this gate proves only that the released reference inference assets are intact.
2. **Apex OpenFPL-method derivative contract.** The paper describes the method-level feature sets and optimization recipe sufficiently to govern a derivative: 1/3/5/10/38-match means, position-specific feature sets, five team-grouped folds, MinMax feature/target scaling, position-specific entropy-bin sample weighting, K-Best Search with K=10 across the published Random Forest/XGBoost search space, and a median ensemble of 50 models per position. `config/openfpl_method_contract.yaml` freezes that method contract. The pinned Dastan `rebuild/features.py` is used only as a non-authoritative independent semantics cross-check for the one-match shift and rolling construction; Dastan's model architecture is not copied. Because upstream training source is absent, any current-rules model built by Apex must identify as `apex-openfpl-method-derivative`; it may never claim exact upstream training reproduction unless separately proven against newly published upstream source.
3. **Current-training readiness.** The published reference was developed on old FPL scoring seasons and uses score-dependent historical feature families including FPL points, relevant FPL points, BPS and bonus over 1/3/5/10/38-match windows. Legacy weights or those score-dependent feature rows therefore cannot be relabelled `fpl-2026-27-v1`. `config/openfpl_training_policy.yaml` is the governed `openfpl-current-training-v1` policy. It requires labels only from completed 2026/27 exact-rule gameweeks, bans all four score-dependent reference player feature families from the derivative feature matrix, permits historical context only when score-independent, and sets a 10-completed-GW construction floor. The resulting governed current feature counts are 176 for GK and 186 for DEF/MID/FWD. Ten completed exact-rule GWs is the earliest construction floor because it spans the reference model's complete short/medium adaptive form family (1/3/5/10 matches) without importing legacy-scoring labels; the 38-match horizon may use score-independent historical context only. A future derivative model must bind to the exact policy and method-contract hashes, declare its exact-rule gameweeks, train strictly before the target GW, use separately hashed training/model artifacts, independently validate feature construction against the pinned reference sample semantics, prove future-placeholder invariance and reach 100% Official DecisionUniverse forecast coverage. Meeting this floor permits only SHADOW model construction.
4. **Prospective serving promotion.** Even a valid current-rules derivative remains `SHADOW`, `serve_authorized=false` and prospectively unqualified. It must accumulate genuine pre-deadline forecasts and pass the same tournament/promotion governance as every other challenger before production authority can change.

Reference inference reproducibility, derivative method validity, current-rule training readiness and prospective serving performance are separate claims. None may be substituted for another, and prospective accuracy can never retroactively validate leakage, stale scoring labels or false provenance.

## Run lifecycle
1. Publish immutable attempt **intent**.
2. Acquire all candidate provider outputs and external evidence.
3. Fetch Official FPL again as the final factual anchor and acquire the manager state from that same authority boundary.
4. Validate provider identity/coverage/freshness and any authenticated manager price state against that anchor.
5. Freeze one content-addressed local snapshot. Acquisition is now closed.
6. Solve from frozen files only. `runtime/solve.py` cannot import source/network modules and the architecture linter enforces this.
7. Certify once.
8. Publish the completed attempt as a GitHub **immutable release**, whether actionable or blocked.
9. After the GW finishes, publish immutable outcome and evaluation releases.
10. Detect an intent without a final release after the grace period as an operational incident.

Required production evidence acquisition is part of step 2, not an optional downstream enrichment. The production config must declare its evidence-record and acquisition-manifest paths. Acquisition itself collects the configured sources before the final Official re-anchor, writes a machine-readable manifest, and fails if a required source did not return usable parseable content. A successful collection may legitimately contain zero external player records; that is distinct from not collecting evidence. The manifest must bind to the same Official authority hash and target gameweek later frozen into the snapshot. Official FPL availability may generate a hard exclusion only for definitive states (for example suspension/unavailability or a zero current-round playing chance paired with a risk status); partial injury/doubt probabilities remain audit evidence. External player claims are attributed at sentence/claim-segment level so a decisive phrase about one named player cannot cross-assign to another player mentioned elsewhere in the same article.

## Exact manager-state boundary
The public `/entry/{id}/event/{gw}/picks/` surface is a locked-deadline record. It can establish the last public squad for HOLD/XI/captain decisions, but it cannot prove the current editable squad, current bank, acquisition prices, selling prices or that no post-deadline transfer has already been made. Public picks therefore never certify `state_complete_for_transfers`.

The public transfer-history surface is frozen as historical evidence as well. Official FPL's public transfer-history UI explicitly states that a viewer who is not logged in as the owner can see transfers only up to the last deadline. Consequently, the absence of a target-gameweek transfer row before its deadline cannot prove that the owner made no transfer. Public transfer rows may be replayed retrospectively after a deadline, but deadline-redacted public state alone never upgrades an editable pre-deadline state to transaction-safe.

For discretionary transfer planning, Apex may consume authenticated Official FPL `/me/` plus `/my-team/{entry_id}/` during the final acquisition/re-anchor step. Authentication material is runtime-only and may be supplied as a browser-session cookie or current `X-API-Authorization` access token. `/me/` must bind the credential to the configured entry before `/my-team` is trusted. The returned state must contain 15 unique current Official IDs, exact purchase/selling prices, bank and coherent current transfer state. Selling prices are re-derived using the frozen Official current market price and the exact half-profit rule; disagreement fails acquisition rather than picking one value by consensus.

Credential material is never part of a snapshot, provider environment or solve input. Instead the snapshot carries `team_state_acquisition.json`, a non-secret provenance record containing the acquisition mode, credential-presence boolean, exact-price counts and public-ledger diagnostics, plus `team_transfers_public.json` containing only the public ledger. If no credential is configured, the system falls back to the public locked squad and withholds discretionary transfers. If a credential is configured but rejected, belongs to another entry or returns incoherent state, acquisition fails closed; it does not silently fall back. An authenticated unlimited/null-limit transfer window is also not treated as an ordinary FT state until chip-aware optimisation explicitly supports it.

The transfer optimiser supports a current-period FT state of 0 through the season maximum. With zero remaining FTs, the next transfer incurs a hit; after the deadline transition, normal rules restore at least the season's first-post-deadline FT allowance.

## Persistence and privacy boundary
Git commits are source code, not production state. Production forecasts/decisions/outcomes use immutable GitHub Releases, but public and private manager data are separate persistence domains.

The public Apex repository may publish only the explicit public allowlist produced by `runtime/publication.py`: public attempt metadata, sanitized canonical/provider forecasts where permitted, public governance, public evidence and attestations. Recursive snapshot publication is forbidden. Raw `TeamState`, exact purchase/selling prices, bank, free transfers, pending chip state and personalized `SystemDecision` are `PRIVATE_MANAGER` and must never be assets of a public release or public Actions diagnostic artifact.

Authenticated attempts require a separate private GitHub repository with release immutability enabled. The repository must be private, distinct from the public Apex repository and initialized with a real default-branch commit before owner credentials are used. The exact manager attempt is persisted there first as an immutable private release. A private release tag is anchored to that private repository's own default branch; it must never use the public Apex code SHA as `target_commitish`, because that commit does not exist in the separate repository. The public code/config/snapshot identities remain cryptographically bound inside the public/private attempt payloads and commitment. Only after the private write verifies may the safe public final be published. The private attempt is bound to the public attempt identity and the public attempt carries a context-bound cryptographic commitment so a post-deadline reveal can prove the personalized decision existed pre-deadline without exposing it beforehand. Public and private attempt identities/hashes must not drift.

`SECRET` credential material is runtime-only and is never persistable in either domain. Browser clients never receive FPL credentials or private GitHub tokens.

Repository-level **Release immutability must be enabled before cutover** for every repository used as a production persistence domain. Releases are built as drafts, exact allowlisted assets are attached and verified, then the release is published. Once GitHub immutability is enabled, its tag and assets are locked and GitHub supplies a release attestation.

Apex also stores SHA-256 manifests inside each bundle. This is defense in depth, not a substitute for GitHub's native immutability.

## Decision semantics
The primary objective is expected submitted FPL points plus captain copy, minus exact transfer hits. Free transfers are not assigned artificial point values. If two transfer plans are equal within numerical tolerance, a second optimization pass minimizes transfer count. Thus flexibility is a tie-break unless evidence demonstrates a measurable EV value.

If only H1 is qualified, discretionary transfers are withheld. The engine still optimizes the submitted XI/captain/bench for the current squad. It does not invent future xP.

If exact current manager-state/selling-price evidence is unavailable, discretionary transfer optimization is withheld. The engine does not assume current market price equals sale value and does not assume the last deadline squad is still the editable squad.

When the serving provider supplies no appearance probabilities, contingent autosub and captain-no-show fallback value are not invented. The decision remains legal and uses unconditional provider xP; certification is degraded with an explicit warning.

## Failure domains
- Official truth failure: blocking.
- Required external-evidence acquisition failure, missing manifest or Official/GW binding mismatch: blocking acquisition/certification failure.
- Authenticated manager-state mismatch/rejection/incoherence when credentials are configured: blocking acquisition failure.
- Missing authenticated manager state when no credentials are configured: transfer planning withheld; current-squad HOLD remains possible from public state.
- Public transfer-history acquisition failure: diagnostic degradation only while manager state is already public/incomplete; it can never manufacture current-state completeness.
- Serving forecast stale/incomplete: blocking unless an explicitly authorized standby independently qualifies.
- Shadow/challenger failure: warning only.
- Optional trusted-media/enrichment failure: warning only.
- Illegal squad/XI/cash state: blocking.
- Private-manager store not private, not initialized, not immutable or unavailable: blocking preflight/publication failure; owner credentials are not used first and the public final is not published as a fallback.
- Private-manager release failure during authenticated mode: blocking; the public final is not published first as a fallback.
- Public/private attempt identity mismatch or public forbidden-field/sentinel detection: blocking publication failure.
- Missing final release after intent: operational failure.
- Snapshot hash mutation: blocking integrity violation.

## Legacy boundary
`src/apex` may never import `src/apex_fpl`. V1 remains live only during migration. After a real V2 pre-deadline lifecycle passes the cutover gate, legacy production workflows and canonical generated-state writers are archived/deleted in the cutover PR.
