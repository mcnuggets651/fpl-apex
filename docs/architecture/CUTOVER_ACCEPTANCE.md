# Apex V2 Cutover Acceptance

Cutover is a binary governance event. A green unit test suite alone is insufficient.

## Repository controls
- [ ] `main` is protected by branch/ruleset controls; force-push and deletion are disabled.
- [ ] Apex V2 CI is a required check for production-code changes.
- [ ] GitHub **Release immutability** is enabled for the public repository before the first production V2 release.
- [ ] A dedicated private Apex manager-state repository exists before authenticated manager mode is enabled.
- [ ] GitHub **Release immutability** is enabled for every private production persistence repository as well as the public repository.
- [ ] The private manager repository is not the public Apex repository and is not an unrelated application repository.
- [ ] Production and evaluation workflows have only the permissions they need.
- [ ] Browser clients never receive FPL credentials, private-repository tokens or other runtime secrets.

## Architecture controls
- [ ] `python scripts/check_v2_architecture.py` passes.
- [ ] No `src/apex` import of `apex_fpl` exists.
- [ ] Decision code cannot import network/source modules.
- [ ] Shadows cannot be represented in production decision inputs.
- [ ] No automatic provider promotion or production ensemble exists.
- [ ] Public/private exposure classes and exact publication allowlists are architecture-tested; unclassified data fails closed.

## Official truth and provider contract
- [ ] Duplicate/unknown Official IDs fail.
- [ ] Price/position/team facts come only from Official FPL.
- [ ] `NO_FORECAST` never counts as coverage.
- [ ] Missing H1 coverage blocks serving.
- [ ] Provider timestamps and run-attempt freshness are checked.
- [ ] AIrsenal export is regenerated during the attempt.
- [ ] A canonical Official FPL hash is captured immediately before provider generation.
- [ ] The final Official FPL hash is reacquired before freeze and must exactly match the pre-provider hash.
- [ ] An Official-hash mismatch aborts before team/provider qualification and requires a new run attempt.
- [ ] Both Official acquisition hashes are persisted in the frozen run provenance.
- [ ] Dastan is generated before the shared freeze in an isolated runtime and remains non-serving while prospectively unqualified.
- [ ] OpenFPL's exact pinned reference checkout passes its structural/inference preflight without being relabelled as current scoring or falsely described as a published trainer.
- [ ] The reference preflight records `INFERENCE_ONLY`, `TRAINING_PIPELINE_NOT_PUBLISHED` and `SAMPLE_CONSTRUCTION_NOT_PUBLISHED` unless newly published upstream source is separately audited.
- [ ] Any Apex-built current-rules implementation uses the distinct identity `apex-openfpl-method-derivative`; it never claims exact upstream training reproduction merely because the paper or reference inference assets are available.
- [ ] `config/openfpl_method_contract.yaml` validates against the pinned OpenFPL and Dastan commits, the 235-column reference sample accounting, exact 1/3/5/10/38 rolling windows, position feature counts, training search space and 50-model median ensemble.
- [ ] Dastan's feature rebuild may be used only as a non-authoritative independent semantics cross-check; its different model architecture is not relabelled as OpenFPL.
- [ ] OpenFPL exact 2026/27 history readiness is pinned and audited independently of the Dastan history role; target/future GW contamination fails closed.
- [ ] `openfpl-current-training-v1` is the governed current-rules construction policy: minimum 10 completed exact-rule GWs, labels only from 2026/27, legacy FPL-points/relevant-points/BPS/bonus feature families excluded, and historical context score-independent only.
- [ ] The governed derivative feature surface is exactly 176 features for GK and 186 for DEF/MID/FWD unless a reviewed contract version changes both code and acceptance tests.
- [ ] Any future current-rules derivative declares `fpl-2026-27-v1`, binds to the exact governed policy and method-contract hashes plus `openfpl-current-nonscore-v1`, declares the exact-rule gameweeks used, meets the 10-GW minimum, uses separately hashed training/model artifacts, trains only through GW < target GW, independently validates its feature construction against reference semantics, proves future-placeholder invariance, reaches 100% Official DecisionUniverse coverage, and explicitly does not reuse legacy reference weights as current weights.
- [ ] Meeting the OpenFPL 10-GW construction floor authorizes only SHADOW model construction; serving authority still requires prospective qualification and an explicit governance change.
- [ ] Dastan/OpenFPL stay non-serving until current-scoring live exports pass the same operational and prospective contract.

## Evidence acquisition
- [ ] Production config explicitly requires the V2 evidence acquisition contract.
- [ ] `apex-v2 acquire` owns required evidence collection; the requirement is not delegated solely to workflow convention.
- [ ] Evidence acquisition emits an immutable-input manifest containing source outcomes, source-config SHA-256, retrieval time, target GW, expected/observed Official hash, record counts and required-source failures.
- [ ] At least one configured Official-league/Official-club source is mandatory; a required Official source outage aborts acquisition.
- [ ] Official FPL status/chance/news availability is captured as Official-league evidence.
- [ ] Only unambiguous Official-league/Official-club absence evidence may create `HARD_EXCLUDE`; uncertain/doubtful states remain audit-only.
- [ ] Trusted-media evidence is structurally `AUDIT_ONLY` and cannot hard-exclude a player.
- [ ] Evidence player identity matching is unambiguous before an external claim is attached to an Official element ID.
- [ ] Evidence timestamps and expiry are validated before solve.
- [ ] A successful collection with zero relevant external player records is distinguishable from a collection that never ran.
- [ ] The evidence acquisition Official hash and target GW exactly match the final Official re-anchor before snapshot freeze.
- [ ] Missing/incomplete evidence acquisition blocks production with `EVIDENCE_ACQUISITION_INCOMPLETE` or a typed acquisition-stage failure.
- [ ] Optional trusted-media outages are recorded as warnings and cannot manufacture hard evidence.

## Team mechanics
- [ ] Exact legal 15/XI/club limits pass property tests.
- [ ] Rolled free-transfer transitions are versioned by season.
- [ ] Current-period free-transfer state supports 0 through the season maximum; a new transfer with 0 remaining FTs incurs the first hit correctly.
- [ ] Selling price uses purchase-price half-profit rules.
- [ ] Existing team value above £100m is not falsely declared illegal.
- [ ] Transfer cash flow and hit cost are exact.
- [ ] Authenticated Official `/me/` must identify the configured Apex entry before `/my-team/{entry_id}/` can be trusted.
- [ ] Authenticated `/my-team/{entry_id}/` must provide 15 unique Official IDs, all purchase/selling prices, current bank and coherent transfer state.
- [ ] Every authenticated selling price is cross-checked against purchase price, the frozen Official current price and the exact half-profit rule.
- [ ] Team-state credentials are injected only during Official acquisition/freeze and are never logged, persisted in snapshots as credentials or exposed to forecast/solve code.
- [ ] A configured but rejected/wrong-entry/incoherent credential fails acquisition; Apex does not silently downgrade to public picks.
- [ ] With no credential, public last-deadline picks remain transaction-incomplete unconditionally and discretionary transfers are withheld.
- [ ] Public transfer history is frozen as evidence with visibility provenance; before a deadline it cannot prove that no hidden current-period transfer has occurred and cannot upgrade public state to transaction-complete.
- [ ] Unlimited/null-limit authenticated transfer windows are withheld from the ordinary transfer optimiser until chip-aware mechanics are explicitly implemented.
- [ ] H1-only evidence withholds discretionary transfers.
- [ ] Incomplete selling-price state withholds discretionary transfers.
- [ ] Execution overlays update squad, bank, owned purchase/selling-price maps and remaining current-period FTs atomically.
- [ ] Secondary tie-break prefers fewer transfers without reducing primary EV.
- [ ] Transfer optimiser infeasibility is returned as typed `INFEASIBLE`, persisted in the DecisionBundle diagnostics, and certifies fail-closed as `BLOCKED` / `DECISION_ILLEGAL` rather than surfacing as an unhandled exception.
- [ ] Public/deadline manager state can never be labelled `personalized_actionable`, `lineup_actionable` or `transfer_actionable` for the current editable team.
- [ ] Authenticated current team state may become `lineup_actionable`; `transfer_actionable` additionally requires exact complete transfer state and a transfer-horizon decision.

## Snapshot/persistence/privacy
- [ ] Intent release is created before external acquisition.
- [ ] All decision inputs are frozen once.
- [ ] Post-freeze input mutation fails integrity checks.
- [ ] Solve phase uses only frozen files.
- [ ] Final attempt release is published even when certification is BLOCKED, subject to the same privacy boundary.
- [ ] Orphaned intent is detected after the grace period.
- [ ] Public release assets are generated from an explicit allowlist; recursive snapshot/archive publication is forbidden.
- [ ] Raw `TeamState`, purchase prices, selling prices, bank, free transfers, pending chips and personalized `SystemDecision` never appear in public release assets or public diagnostic artifacts.
- [ ] Randomized private sentinel values are absent from every public file, public tar member and diagnostic artifact during privacy rehearsal.
- [ ] Provider metadata is sanitized before public persistence and cannot carry private manager fields by accident.
- [ ] Authenticated production publishes the immutable private manager attempt first; public final publication is refused if the private write/verification fails.
- [ ] Private and public attempts are bound to the same run/code/config/Official/canonical identity and cannot drift.
- [ ] A context-bound cryptographic commitment proves the private personalized decision existed pre-deadline without disclosing it pre-deadline.
- [ ] Reveal verification rejects pre-deadline reveal, wrong attempt identity, tampered decision bytes and wrong commitment key.
- [ ] Public `official_snapshot_sha256` and `canonical_projection_sha256` are non-empty valid 64-hex digests sourced from the canonical DecisionBundle fields.
- [ ] Public canonical rows include only the contiguous qualified serving horizon; no unqualified provider horizon is exposed as canonical.
- [ ] Public and private bundle/asset hashes are verified.
- [ ] Native immutable-release status is verified during cutover for every production persistence repository.

## Evaluation
- [ ] Outcomes are collected only after Official FPL marks the GW finished.
- [ ] Forecasts are evaluated from the frozen pre-deadline release, never regenerated.
- [ ] Metrics are player-gameweek grain.
- [ ] All-player and 60+ minute cohorts are reported.
- [ ] Evaluation releases cannot change provider authority.

## Live dress rehearsal
- [ ] One genuine pre-deadline V2 intent is published.
- [ ] Official pre-provider seal succeeds.
- [ ] Fresh AIrsenal generation succeeds.
- [ ] Optional challenger generation occurs before freeze and cannot invalidate the serving incumbent merely by failing.
- [ ] Required V2 evidence acquisition succeeds and its manifest is bound to the same Official hash/GW as the final snapshot.
- [ ] Official post-provider seal exactly matches the pre-provider seal.
- [ ] Official final anchor and snapshot freeze succeed.
- [ ] A public-fallback rehearsal explicitly records conditional/non-personalized action scope and never masquerades as the owner's current editable team.
- [ ] Before cutover, a separate authenticated rehearsal must acquire the current editable team, exact purchase/selling prices, bank, remaining FT state and pending chip state, and must bind `/me/` to the configured entry.
- [ ] Solver completes from frozen state or emits a typed/persisted blocking decision diagnostic.
- [ ] Public safe release and, for authenticated mode, private manager release become immutable and verify.
- [ ] Public release contains non-empty Official/canonical hashes, a coherent qualified horizon and no private sentinels/fields.
- [ ] Authenticated rehearsal reaches coherent manager action scope; transfer actionability is granted only when exact transfer state and the transfer optimiser are valid.
- [ ] Recommendation is legal and certification/action scope are coherent.
- [ ] The sealed personalized decision is adversarially checked against Official prices, current squad, bank, FTs, chip state, XI/captain/vice/bench and transfer legality before cutover.
- [ ] After the GW, outcome/evaluation releases are produced.

Only after every applicable item is proven do we merge the cutover PR that retires V1 production writers/workflows.
