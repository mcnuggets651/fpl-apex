# Apex release certification contract v2 — 2026-08-23

## Objective

A green optimiser is not sufficient evidence that Apex is safe to act on. Release certification must prove that one sealed generation is internally coherent, independently solvable, mechanically executable, appropriate to the current FPL lifecycle, adversarially tested on the correct decision surface and promotable without post-certification repair.

The previous v1 contract made a structural mistake: it treated GW1 launch sensitivity and launch-squad bench reconstruction as universal release gates. In GW2 this caused a valid receding-horizon canonical solve to be rejected by a launch-only adversarial audit. The fix is not to skip adversarial testing; it is to make the selector determine the required certification profile.

## Architecture

There is one live PR release transaction: `.github/workflows/adaptive-canonical-diagnostic.yml`.

`Apex Adaptive Strategy Audit` is now a focused deterministic lifecycle-contract gate. It does not refresh Official FPL, AIrsenal, clone the independent solver or run a second copy of the live release transaction.

`Apex Unified Readiness Audit` reuses the canonical diagnostic transaction instead of maintaining another orchestration copy.

`Apex Unified` remains the only production publisher. It invokes the same Python release certifier before production finalization and compare-and-swap publication.

Selector/lifecycle rules live in `src/apex_fpl/services/release_profile.py`, not in workflow names or duplicated YAML.

## Release profiles

### `pre_gw1_launch`

Selector: `adaptive_gw1_launch_with_transfer_option_value`.

Required state:

- actionable horizon begins at GW1;
- no published personal deadline squad exists.

Required sensitivity:

- `apex-adversarial-launch-ban-v2`;
- hardened candidate-pool stability;
- GW1 regret-floor compliance;
- hostile force/ban perturbations with no search-surface defect signal or inconclusive solve.

### `in_season_receding_horizon`

Selector: `receding_horizon_current_team_maximum_ev`.

Required state:

- healthy sealed personal team state;
- published deadline squad exists;
- next actionable GW is later than the published GW;
- exact 15-player realised selling-price state.

Required sensitivity:

- `apex-inseason-action-sensitivity-v1`;
- fresh same-bundle unconstrained replay must reproduce the published transfer action and objective;
- exact roll counterfactual;
- no-hit counterfactual capped at current free transfers;
- exact published transfer-count replay;
- one-fewer and one-more transfer counterfactual where legal;
- every counterfactual must be Optimal or solver-certified Infeasible; limits/errors/input failures are blockers;
- no constrained counterfactual may beat the supposedly unconstrained baseline.

The transfer MILP therefore supports first-GW-only min/max transfer-count constraints. Hit costs remain inside the normal objective. There is no arbitrary rule forbidding a large hit: a large hit must survive the same-surface counterfactual proof.

## Common gates

Both profiles require:

- one DecisionBundle identity across manifest, canonical, answer context, Pinnacle, parity, sensitivity and bench stress;
- `strategy_stage=final_validated`;
- canonical and answer-context ready/safe flags;
- 100% certified hard-fact/canonical-projection/AIrsenal-or-governed-fallback coverage;
- independent parity on `pinnacle_ev`;
- 15 unique squad IDs and 11 unique XI IDs;
- captain and vice inside the XI and distinct;
- final evidence dossiers matching exactly the canonical 15;
- selector-neutral `apex-bench-stress-v2` on the actual canonical submission;
- dry-run `promote_certified_generation.py` into an isolated target.

For in-season output, `action_now` must also agree with the top-level exact mechanics on squad, ordered XI, captain, vice, bench goalkeeper, ordered outfield bench and exact expected points.

## Bench stress v2

Bench stress no longer reconstructs a GW1 launch squad. It consumes the exact canonical 15/XI/captain/vice/bench for the current actionable GW and evaluates one- and two-starter absence scenarios while keeping the submitted bench order fixed. It never reorders with hindsight.

## Public FPL state boundary

FPL publicly exposes another manager's transfers only up to the last deadline. The live current team requires the authenticated `my-team` surface. Therefore a public entry snapshot is exact only if the manager has not made undisclosed post-deadline moves.

Apex preserves this boundary:

- public deadline state is sealed with exact selling prices and transfer-history provenance;
- the in-season sensitivity certificate records `public_deadline_snapshot=true` when applicable;
- it emits a warning that a manual override is required if the manager has already changed the team;
- Apex does not fabricate private transfer knowledge.

## Failure observability

`release_generation_certificate.json` is now contract `apex-release-generation-certificate-v2` and is written at the start of certification, updated after every gate, and preserved on failure.

It records:

- run ID;
- DecisionBundle ID;
- selector;
- lifecycle;
- per-gate status;
- blockers and warnings;
- sensitivity contract/summary;
- mechanics proof;
- dry-run promotion status.

The CLI exits non-zero when `ready=false`, but the failed certificate remains in the workflow artifact. A red release should therefore identify the actual failed gate instead of ending with only a generic child-process exit.

## Workflow ownership

- **Apex CI:** full pytest, Ruff, upstream/governance contracts.
- **Apex Adaptive Strategy Audit:** fast deterministic lifecycle/release contract tests.
- **Apex Canonical Diagnostic:** sole live PR release transaction.
- **Apex Unified Readiness Audit:** manual reuse of Canonical Diagnostic; never publishes.
- **Apex Unified:** sole main publisher, guarded by the same release certifier and compare-and-swap.

This separation prevents workflow copies from drifting while retaining independent model/data audits and one production publication authority.

## Fail-closed rule

There is no cross-lifecycle fallback. A launch selector cannot be certified with an in-season audit and an in-season selector cannot be certified with a launch audit. Unknown selector, lifecycle mismatch, missing state proof, inconclusive counterfactual, cross-artifact identity mismatch, mechanics mismatch, bench-stress violation or failed dry-run promotion blocks publication.