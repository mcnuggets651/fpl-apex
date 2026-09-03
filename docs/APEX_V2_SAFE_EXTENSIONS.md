# Apex V2 Safe Extensions

## Status and immutable boundary

These extensions are an operations, presentation and evaluation layer around the certified Apex V2 engine. They do not alter the production engine.

Frozen engine SHA:

`99cc7b51b0cff45462b567084cb1844cfe0a456f`

The following remain invariant:

- AIrsenal is the sole serving champion for H1-H8.
- Dastan, Apex Proprietary and PITCHSIDE remain non-serving challengers/shadows.
- OpenFPL remains governed diagnostic/research only until its independent readiness contract is satisfied and a legitimate model is separately built.
- no blending, voting or automatic promotion is permitted;
- canonical xP construction, provider qualification, optimizer objective, transfer mechanics, captain mechanics and immutable production publication are untouched;
- Price Risk remains outside the serving engine;
- PR #90 remains frozen and does not need to merge.

Every extension is one-way. It may schedule, render, seal or score evidence around a canonical decision, but it may not write information back into production xP, the optimizer, serving-provider authority or an already published recommendation.

---

## 1. Actual-deadline-aware production refresh

Workflow: `.github/workflows/apex-v2-deadline-watch.yml`

Controller: `scripts/apex_v2_deadline_ops.py`

The 04:17 UTC daily production run remains the baseline. The deadline watcher may dispatch at most one additional production refresh when the current Official FPL deadline is between 90 and 150 minutes away. It runs at minute 11 and 41 of each hour and resolves the deadline from current Official FPL data rather than assuming a weekday or kickoff pattern.

Before dispatch it verifies whether any workflow-dispatch production run already exists inside the current Official deadline window. Queued, running, successful and failed runs all satisfy deduplication. The watcher has no manager credentials, private repository token or model dependencies. It cannot acquire, solve or publish; it can only dispatch the already-governed production workflow on `main`.

The production workflow itself remains unchanged: frozen engine checkout, shared auth concurrency, exact manager reauthentication, Official re-anchor, one frozen snapshot, offline solve and immutable publication.

---

## 2. Owner-private read-only decision brief

Workflow: `.github/workflows/apex-v2-owner-brief.yml`

Controller: `scripts/apex_v2_owner_brief_ops.py`

Private release namespace:

`apex-v2/private-presentation/<season>/<production-run-id>`

After a successful production run, the owner brief renders the already sealed recommendation into structured JSON, compact Markdown and an attestation bound to the immutable private manager attempt. It does not recompute a recommendation.

It surfaces actionability, transfer/roll, XI, captain/vice, bench order, bank, free transfers, active chip, H2-H3 plan, Official deadline, source identities and sealed warnings. Player identity comes only from the immutable Official catalog contained in the private canonical forecast. Missing identity fails closed.

The contract records `production_influence = NONE` and `serving_authorized = false`. No public manager-state artifact is created.

---

## 3. Retrospective canonical decision-quality diagnostics

Workflow: `.github/workflows/apex-v2-decision-quality.yml`

Controller: `scripts/apex_v2_decision_quality_ops.py`

Legacy/private release namespace:

`apex-v2/private-decision-quality/<season>/<production-run-id>`

The existing V1 diagnostics are retained for backward compatibility and continue to score only an immutable production decision after the frozen evaluator has published immutable `outcomes.json`.

They measure captain/vice fallback, captain regret within the sealed XI, pre-autosub lineup regret within the final owned 15, bench points, transfer in/out same-GW delta, zero-minute starters, expected-minutes coverage and final-squad minutes MAE. These remain observational diagnostics and do not infer total-team transfer regret or long-horizon counterfactual value.

The V1 release remains owner-private, immutable and explicitly non-serving.

---

## 4. Prospective decision-edge lab

The decision-edge lab answers a different and more important question than forecast MAE:

> When models disagreed before the deadline, would acting on that disagreement actually have produced a better FPL decision?

Forecast accuracy and decision quality remain separate evidence streams. A provider can have better expected-minutes MAE without changing any transfer, XI, captain or bench choice; conversely, a small forecast difference can matter greatly if it changes a marginal decision. The lab therefore measures both.

### Lifecycle

The no-hindsight sequence is:

`immutable production final -> tournament-ready predeadline candidate -> private decision lab -> deadline -> canonical tournament selection -> immutable Official outcome -> private decision edge -> sequential learning`

Private release namespaces:

- per-task predeadline staging: `apex-v2/private-decision-lab-task/<season>/<production-run-id>/<control-plane-fingerprint>/<task-name>`;
- canonical predeadline lab: `apex-v2/private-decision-lab/<season>/<production-run-id>`;
- realized edge: `apex-v2/private-decision-edge/<season>/obs<N>`;
- rolling learning: `apex-v2/private-decision-edge-learning/<season>/through-obs<N>`.

All four namespaces are owner-private research derived from exact manager state and therefore use the existing frozen `PRIVATE_MANAGER` exposure class. They do not introduce a new exposure class. Each release is immutable, uses an exact asset allowlist plus attestation, records no serving authority, and remains in the private repository.

The `fpl` query bridge does not consume any of these decision-lab namespaces. Its serving/read bridge uses exact reviewed namespace matching rather than a generic `apex-v2/private*` prefix, so the lab, task, edge and learning releases cannot become current manager decisions by namespace collision.

The task namespace exists only to make the predeadline matrix bounded, resumable and control-plane-versioned. A task release is an implementation staging artifact, not a serving or query-bridge surface. The canonical lab remains the immutable historical record of the controller version that actually sealed that production run.

A lab is created only from a tournament-ready immutable candidate while its Official deadline is still in the future. If no lab was sealed before the deadline, that candidate can never be retrospectively backfilled. Missing predeadline evidence stays missing.

### Exact production baseline reproduction

Before any challenger counterfactual is accepted, the controller reconstructs the same Official snapshot, exact team state, hard exclusions, AIrsenal surface and planning horizon used by production, then reruns the frozen transfer optimizer.

The resulting squad, transfers, XI, captain, vice, bench order and hit count must exactly match the immutable production decision signature. Any mismatch fails the lab. This prevents a shadow experiment from comparing against an approximate or differently configured baseline.

The production optimizer source itself is never modified: the workflow checks out the frozen engine SHA and materializes only non-serving operations controllers from the current control-plane SHA.

### Provider-neutral experiment classes

For every legitimate sealed H1 challenger, Apex attempts the same pre-registered experiments. Provider names receive no prior advantage, including Dastan.

#### 1. H1 mechanics on the production squad

The production transfers/final 15 are held fixed. The challenger H1 surface chooses XI, captain, vice and bench using the frozen mechanics code.

This isolates lineup/captain/bench value from transfer planning.

#### 2. Challenger H1 + AIrsenal H2-H8 planning

The challenger supplies the complete H1 forecast surface while AIrsenal supplies future planning horizons. The frozen transfer optimizer is rerun.

This is the principal experiment for an H1-only provider such as Dastan: it can prove that its short-term signal improves today's transfer and mechanics decision without inventing Dastan forecasts for future Gameweeks.

#### 3. Challenger availability on unchanged AIrsenal xP

AIrsenal expected points remain byte-for-byte conceptually authoritative for the experiment. Only a challenger availability field is substituted when that exact field has 100% coverage across the predeadline decision universe.

Eligible fields are expected minutes, appearance probability, start probability and 60-minute probability. Missing values are never filled from another provider and expected points are never rescaled or reverse-engineered from expected minutes.

This matters because the frozen optimizer does not directly optimize expected minutes. A minutes model should only receive decision credit when its actual scoreable availability fields cause a better submitted FPL decision.

#### 4. Pure-provider contiguous plan

A pure challenger transfer plan is attempted only when the challenger genuinely owns a complete contiguous H1-HN surface with N >= 2. H1-only providers are recorded as `NOT_SUPPORTED_H1_ONLY_OR_INCOMPLETE_H2`; no future rows are fabricated.

### Explicit experiment accounting

Every challenger receives an experiment matrix. A missing variant is not silently omitted. It is recorded as one of the explicit states such as sealed, no complete availability field, H1 incomplete, optimizer produced no decision, or H2 unsupported/incomplete.

### Exact realized FPL scoring

After the canonical tournament selection and immutable Official outcome exist, each prospectively sealed variant is scored with FPL mechanics rather than raw selected-player sums:

- legal submitted formation is verified;
- goalkeeper autosub is handled separately;
- outfield substitutions respect submitted bench priority and legal formation minima/maxima;
- captain falls back to vice only on captain non-appearance;
- transfer hits use the frozen season rule cost;
- Triple Captain applies the correct two additional captain copies;
- Bench Boost scores the exact submitted full 15, including zero-minute players with their realized zero;
- unknown future chip semantics fail closed instead of being guessed.

The output stores `realized_points_after_hits` and the direct point edge versus the immutable production baseline. It also records whether the counterfactual actually changed the decision signature.

Every realized edge additionally carries the full `decision_lab_control_plane_sha` from the prospectively sealed lab. Missing or malformed control-plane identity fails closed; it is not inferred from publication time, provider name or a later controller revision.

### Sequential decision-edge learning

Decision-edge evidence updates after every completed canonical H1. Twelve Gameweeks are not a waiting period.

Evidence is cohort-isolated by the prospectively sealed decision lab's full control-plane SHA. The same stable `variant_id` under two different controller implementations is not counted as replication. Each implementation cohort must earn its own observation count and review stage. This preserves immutable historical evidence while preventing a controller rewrite or bugfix from silently pooling semantically different experiments.

The recent evidence has a four-observation half-life. Stages are deliberately progressive:

- one observation: `DIAGNOSTIC_SIGNAL`;
- repeated positive evidence: `EMERGING_EDGE`;
- two unanimous large wins of at least four recency-weighted FPL points: `FAST_TRACK_REVIEW_ELIGIBLE`;
- three or more consistent material wins: `ACTIONABLE_SPECIALIST_REVIEW`;
- five or more stronger consistent wins: `SPECIALIST_ROLE_CANDIDATE`;
- later samples may progress to `STRONG_EVIDENCE` and `MATURE_EVIDENCE`.

A review-eligible edge creates an owner review item. It still does not alter production. Every report records:

- `exposure_class = PRIVATE_MANAGER`;
- `production_influence = NONE`;
- `serving_authorized = false`;
- `promotion_authority = false`;
- `automatic_serving_change = false`;
- `cross_control_plane_pooling = false`;
- `serving_action = NO_AUTOMATIC_CHANGE`.

Any future specialist role, blend or champion change must be a separate explicit governed/versioned production change.

### Workflow ordering

`Apex V2 Decision Quality` now runs after either:

- successful `Apex V2 Prospective Tournament`, so a newly available predeadline candidate can be sealed into the private lab immediately; or
- successful `Apex V2 Daily Evaluation`, so completed outcomes can be scored and rolling edge evidence advanced.

It retains `contents: read` only in the public repository and writes research material only to the already governed private immutable release store.

---

## 5. What remains intentionally unchanged

This work does not:

- change a single file under the frozen `src/`, `config/` or engine `tests/` trees;
- alter the frozen engine SHA;
- merge or depend on PR #90;
- change AIrsenal H1-H8 serving authority;
- auto-promote Dastan or any other challenger;
- blend challenger xP into production;
- create postdeadline counterfactual forecasts;
- regenerate a missing predeadline lab after outcomes are known;
- move Price Risk into serving optimization;
- alter the 04:17 UTC baseline production run;
- add a second production publisher;
- grant the decision-quality workflow public `contents: write` permission.

---

## 6. Acceptance criteria

This extension is complete only when all of the following hold:

1. targeted realized-scoring tests cover formation-aware autosubs, goalkeeper fallback, captain-to-vice fallback, transfer hits, Triple Captain, Bench Boost and unknown-chip fail-closed behavior;
2. availability-overlay tests prove AIrsenal xP is never changed and incomplete fields are not silently used;
3. sequential edge tests prove one-GW diagnostic learning, early fast-track review and zero automatic serving authority;
4. provenance regressions prove every realized edge carries a valid decision-lab control-plane SHA, missing identity fails closed, and identical `variant_id` evidence from different controller SHAs is never pooled as replication;
5. exposure regressions prove private lab/edge/learning artifacts remain inside the frozen `PRIVATE_MANAGER` class rather than inventing a new classification token;
6. existing V1 decision-quality tests continue to pass;
7. the entire `ops_tests` suite passes against the exact frozen evaluator/engine source;
8. the ops contract proves no frozen-engine path changed;
9. the decision-quality workflow remains read-only in the public repository and has no acquire/solve/production-publish/provider-generation command;
10. broad repository pytest, Ruff, upstream and governance checks are green;
11. after merge, the push-triggered decision-quality run successfully seals or verifies the current still-predeadline GW3 lab without invoking production;
12. production and PR #90 identities are reverified after merge.

Once these criteria pass, future observations are ordinary operation of the prospective learning system rather than a new architecture exercise.
