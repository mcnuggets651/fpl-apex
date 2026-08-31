# Apex V2 Safe Extensions

## Status and immutable boundary

These extensions are an **operations/presentation/evaluation layer around** the certified Apex V2 engine. They do not alter the engine.

Frozen engine SHA:

`99cc7b51b0cff45462b567084cb1844cfe0a456f`

The following remain unchanged by this work:

- AIrsenal is the sole serving H1-H8 champion.
- Dastan, PITCHSIDE and Apex Proprietary remain nonserving challengers/shadows.
- OpenFPL remains diagnostic-only.
- xP construction, solver objective, transfer mechanics, captain mechanics, provider qualification and immutable publication are untouched.
- Price Risk remains outside the serving engine.
- PR #90 does not need to merge for these extensions to operate.

The extensions are intentionally one-way. They may **schedule**, **render** or **score** a sealed Apex decision; they may not write information back into canonical xP or the optimizer.

---

## 1. Actual-deadline-aware production refresh

Workflow: `.github/workflows/apex-v2-deadline-watch.yml`

Controller: `scripts/apex_v2_deadline_ops.py`

### Objective

The 04:17 UTC daily production run remains the baseline. The deadline watcher adds at most one additional automatic production refresh when the current Official FPL deadline is between **90 and 150 minutes away**.

The watcher runs at minute `11` and `41` of every hour. The 60-minute eligibility window plus 30-minute polling cadence gives more than one opportunity to observe the window without repeatedly running the expensive production engine.

### Authority

The watcher reads the current `bootstrap-static` response every time. It does not assume Friday, Saturday, a fixed kickoff pattern or a locally configured Gameweek date.

The next target is the earliest strictly future valid Official FPL event deadline. Any unfinished positive-ID Official event with an invalid/missing deadline makes the watcher fail closed rather than silently skipping that event.

If Official FPL moves a deadline, the next watcher evaluation uses the moved deadline automatically.

### Deduplication and retries

Before dispatch, the watcher lists `Apex V2 Daily Production` workflow-dispatch runs and asks whether **any manual/automatic workflow-dispatch production run was created inside the current Official deadline window**.

If one exists, the window is already satisfied. This includes a successful, failed, queued or in-progress production run. Therefore:

- a failed near-deadline production does not trigger automatic reassurance retries;
- an extraordinary manually requested production inside the same window also satisfies the refresh requirement;
- the normal 04:17 scheduled production does not count as the deadline-window refresh because its event is `schedule`, not `workflow_dispatch`.

The watcher has a non-cancelling concurrency group, so two watcher instances cannot race each other into duplicate dispatches.

### Failure behavior

The watcher fails closed if:

- Official FPL does not return a parseable future deadline;
- the GitHub workflow-run history cannot be verified;
- the watcher is not running on `main`;
- the dispatch request is rejected.

It has **no manager credentials, no private repository token and no model/provider dependencies**. It cannot create an Apex intent, acquire data, solve or publish. The only privileged action it can perform is dispatch the already-existing production workflow on `main`.

The production workflow itself is unchanged. It still checks out the frozen SHA, shares auth concurrency, re-authenticates the exact manager, re-anchors Official truth, freezes once, solves offline and publishes immutably.

---

## 2. Owner-private read-only decision brief

Workflow: `.github/workflows/apex-v2-owner-brief.yml`

Controller: `scripts/apex_v2_owner_brief_ops.py`

Private release namespace:

`apex-v2/private-presentation/<season>/<production-run-id>`

### Objective

Apex's machinery is deliberately complex, but the owner-facing decision should be simple. After a successful production workflow, the owner-brief workflow renders the already sealed decision into:

- `owner_brief.json` — structured machine/read-only presentation contract;
- `owner_brief.md` — compact human-readable decision surface;
- `owner_brief_attestation.json` — hashes tying the brief to the immutable private manager attempt.

### Inputs

The renderer requires a matching pair of immutable releases:

- public final `apex-v2/final/...`;
- private manager attempt `apex-v2/private/...`.

It verifies the public attestation, private attestation, public/private attempt identity, target Gameweek and private source SHA-256 before rendering.

### Content

The brief surfaces, without recomputation:

- `ACTIONABLE` / `NOT_ACTIONABLE` from the sealed certification + manager-actionability contract;
- transfer/roll decision;
- XI;
- captain and vice-captain;
- bench order;
- bank, free transfers and active chip when available;
- H2-H3 plan filtered by the sealed `TransferWeek.horizon` values 2 and 3 (never by list position), with Official player labels;
- target GW, Official deadline, frozen timestamp and source hashes;
- serving-provider map as diagnostic metadata;
- warnings/reasons from the sealed certification.

Player names, positions and prices are resolved only from the immutable Official catalog inside the private canonical forecast. No live lookup is used. Missing/incomplete Official identity for any sealed player is fatal rather than replaced by a synthetic label.

### Privacy and authority

The brief is stored only in the existing private immutable repository. Nothing from the private manager payload is uploaded as a public Actions artifact or public release.

Its contract explicitly records:

- `production_influence = NONE`;
- `serving_authorized = false`;
- no xP recomputation;
- no player reranking;
- no transfer alteration;
- no challenger blending.

If certification or manager actionability is absent/false, the display fails closed to `NOT_ACTIONABLE`.

A presentation failure occurs after production has already succeeded and cannot invalidate or replace the canonical production release.

---

## 3. Retrospective decision-quality diagnostics

Workflow: `.github/workflows/apex-v2-decision-quality.yml`

Controller: `scripts/apex_v2_decision_quality_ops.py`

Private release namespace:

`apex-v2/private-decision-quality/<season>/<production-run-id>`

### Lifecycle ordering

Decision quality never fetches a match result itself. It waits for the frozen evaluator to publish immutable:

`apex-v2/outcome/<season>/<run-id>/outcomes.json`

Only then does the separate decision-quality workflow combine that immutable post-GW outcome with the matching immutable pre-deadline private manager attempt.

This ordering makes the no-hindsight boundary explicit:

`sealed decision -> Official GW completes -> frozen evaluator seals outcome -> retrospective diagnostic`

The workflow is triggered only after successful `Apex V2 Daily Evaluation`, plus manual/post-change acceptance triggers. It has no schedule of its own.

### Metrics

V1 records decision-facing diagnostics that can be calculated exactly from the sealed state without speculative counterfactuals:

#### Captaincy

- sealed captain and vice;
- effective captain after the ordinary captain-no-appearance/vice-appearance fallback;
- realized captain bonus;
- best realized captain bonus among the **sealed XI**;
- captain-bonus realized regret.

Captain regret is deliberately conditional on the chosen XI. It does not pretend a benched player's score was an available captain choice without also changing the lineup.

#### Starting XI / bench

- selected XI realized points before autosubs;
- best hindsight legal FPL XI within the owned final 15;
- pre-autosub XI realized regret;
- bench realized points;
- zero-minute selected starters;
- bench players who appeared.

The best-XI calculation enforces the actual legal formation bounds: one goalkeeper, 3-5 defenders, 2-5 midfielders and 1-3 forwards.

#### Transfers

- free transfers before the decision;
- whether Apex rolled/held;
- sealed transfers in/out;
- same-GW incoming realized points;
- same-GW outgoing realized points;
- same-GW transferred-player incoming-minus-outgoing points delta when the transfer counts match;
- recorded transfer-hit field.

The transferred-player delta is **not total team regret**: it does not pretend the incoming and outgoing players would necessarily occupy identical XI/bench roles. The diagnostic deliberately **does not infer hit cost or long-horizon transfer value** from the same-GW result. Those require a different longitudinal counterfactual study.

#### Minutes

- H1 expected-minutes coverage over the final 15;
- H1 expected-minutes MAE over covered final-squad players.

This helps distinguish a poor FPL decision from a minutes/availability forecasting miss.

### Governance

Decision-quality outputs are owner-private and immutable. The contract declares:

- `production_influence = NONE`;
- `serving_authorized = false`;
- `promotion_authority = false`.

These metrics can identify research questions at formal reviews. They do not themselves promote a challenger, alter AIrsenal authority, modify xP or rewrite a historical recommendation.

---

## 4. What remains intentionally unchanged

This work does **not**:

- add another challenger;
- blend existing challengers;
- move Price Risk into serving optimization;
- alter the daily 04:17 UTC baseline production;
- add a second publisher;
- add repeated near-deadline production retries;
- alter authenticated manager acquisition;
- change any file under `src/`, `config/` or the frozen `tests/` tree;
- alter the frozen engine SHA;
- require PR #90 to merge.

## 5. Acceptance criteria

The safe extensions are complete only when all of the following are true:

1. new pure-controller unit tests pass;
2. the entire existing `ops_tests` suite passes;
3. repository governance recognizes all three workflows;
4. the ops contract proves no frozen-engine path changed;
5. deadline watcher is statically unable to call serving/solve/publish commands;
6. owner brief and decision quality have public-repo `contents: read` only and private release storage only;
7. the unchanged production workflow retains the certified frozen SHA and 04:17 schedule;
8. broad repository pytest/ruff/upstream/governance/readiness CI is green;
9. merge-time push acceptance runs the deadline watcher safely outside the current window, creates/verifies the latest private owner brief, and runs decision-quality backfill/no-op from immutable completed outcomes without invoking production.

A future near-deadline production run is then ordinary operation of the already-certified publisher, not a new rehearsal or engine certification event.
