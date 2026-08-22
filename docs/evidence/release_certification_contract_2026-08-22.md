# Apex release certification contract — 2026-08-22

## Objective

A green optimiser is not sufficient evidence that Apex is safe to act on. Release certification must prove that one sealed generation is internally coherent, independently solvable, adversarially stable, mechanically executable and promotable without mutating or repairing its certified decision after the fact.

The release contract is implemented once in `scripts/certify_release_generation.py` and is used by both PR certification and `main` production.

## Lifecycle

### Pull request

`Apex Canonical Diagnostic` is the canonical release-candidate transaction. It:

1. creates an empty run-scoped generation;
2. refreshes genuine AIrsenal forecasts;
3. refreshes Official FPL immediately before sealing;
4. builds one actionable-horizon DecisionBundle;
5. builds Pinnacle on that bundle;
6. runs and embeds same-surface independent solver parity;
7. runs canonical Apex;
8. invokes the complete release certifier;
9. uploads the entire generation and certificate.

`Apex Adaptive Strategy Audit` is a thin reusable-workflow caller of that exact transaction. It exists as a distinct required PR check without maintaining a second divergent implementation.

### Main production

`Apex Unified` runs the same `certify_release_generation.py` after canonical assembly and before production finalization/promotion.

The production finalizer receives `--canonical-step-succeeded` only when both:

- canonical assembly exited successfully; and
- the complete release certificate exited successfully.

A release-certificate failure therefore enters the normal fail-closed production path and cannot inherit `ready_to_act=true` merely because canonical assembly completed.

## Release certificate invariants

The certifier requires all release surfaces to share one non-empty DecisionBundle identity:

- DecisionBundle manifest;
- canonical recommendation;
- answer context;
- Pinnacle;
- independent solver parity;
- adversarial sensitivity audit;
- submitted-bench stress audit.

It requires:

- canonical `strategy_stage=final_validated`;
- canonical strategy base ready;
- canonical `ready_to_act=true`;
- answer context `safe_to_act=true` and `ready_to_act=true` with no blockers;
- Pinnacle ready;
- all-player truth ready with 100% certified hard-fact, canonical projection and AIrsenal-or-governed-fallback coverage;
- parity on the `pinnacle_ev` comparison surface;
- adversarial audit complete with no search-surface defect signals and no ban-solve errors;
- submitted-bench stress fixed to the certified submission with no hindsight reordering;
- exactly 15 unique squad identities and 11 unique XI identities;
- distinct captain and vice-captain inside the XI;
- final evidence dossiers covering exactly the canonical 15.

For in-season `receding_horizon_current_team_maximum_ev`, the certifier additionally requires `action_now` to use the independent exact current-Gameweek mechanics authority and to match the canonical top-level result on:

- exact 15;
- ordered XI;
- captain;
- vice-captain;
- bench goalkeeper;
- ordered outfield bench;
- exact expected total points.

## Mandatory stress certificates

Before a release certificate is issued, the certifier runs:

- mandatory adversarial selection sensitivity (`run_adversarial_launch_ban.py` + `certify_adversarial_launch_ban.py`);
- mandatory submitted-XI bench stress (`audit_bench_stress.py`);
- a dry-run `promote_certified_generation.py` transaction into an isolated temporary target.

The dry-run promotion must emit `certified_generation.json`; a copy is sealed into the run artifact as `dry_run_certified_generation.json`.

The final certificate is written as `release_generation_certificate.json` with contract `apex-release-generation-certificate-v1`.

## Workflow-evaluation safety

GitHub's `runner` context is step/runner scoped and must not be used in job-level environment evaluation. A prior Adaptive workflow used `PROMOTION_DIR: ${{ runner.temp }}/...` at job level, which prevented the workflow from being instantiated. Promotion targets used during graph evaluation are now plain job-safe paths; `RUNNER_TEMP` is used only inside runner-executed steps.

`tests/test_release_workflow_contract.py` permanently checks:

- Canonical remains reusable and invokes the release certifier;
- Adaptive remains a thin caller of Canonical rather than a drifting duplicate;
- job-level `runner.temp` promotion wiring does not return;
- Unified requires the release certificate before it can mark canonical finalization successful.

## Fail-closed rule

There is no release fallback. A missing certificate, cross-artifact identity mismatch, mechanics mismatch, adversarial defect signal, bench-stress violation or failed dry-run promotion blocks actionable publication. The correct response is to preserve the failed generation for diagnosis and withhold the recommendation, not to repair the published payload after certification.
