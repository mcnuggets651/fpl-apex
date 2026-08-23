# APEX Migration From PR #66

Status: Slice 0 inventory complete  
Historical PR: #66 (`agent/fpl-specialist-evidence`)  
Policy: reference / archaeology / regression source only. Do not merge or cherry-pick wholesale.

GitHub returned 139 changed paths on 23 August 2026. Every path is accounted for below.

## PORT_AFTER_REFACTOR

Retain validated logic/policy, but move it behind V2 ports, registries, sealed-world/runtime boundaries and proof contracts.

- `.github/workflows/adaptive-canonical-diagnostic.yml`
- `.github/workflows/apex.yml`
- `.github/workflows/joint-path-promotion-audit.yml`
- `.github/workflows/pinnacle.yml`
- `.github/workflows/production-readiness.yml`
- `.github/workflows/projection-policy-audit.yml`
- `.github/workflows/projection-shadow-audit.yml`
- `.github/workflows/refresh-core-pin.yml`
- `.github/workflows/team-strength-validation.yml`
- `.github/workflows/understat-player-production-ab.yml`
- `config/apex.yaml`
- `config/news_sources.yaml`
- `src/apex_fpl/config.py`
- `src/apex_fpl/data/airsenal.py`
- `src/apex_fpl/data/entry.py`
- `src/apex_fpl/data/odds.py`
- `src/apex_fpl/data/tactical.py`
- `src/apex_fpl/evaluation/team_goals.py`
- `src/apex_fpl/models/fixtures.py`
- `src/apex_fpl/models/projection.py`
- `src/apex_fpl/models/team_goals.py`
- `src/apex_fpl/optimisation/bench_policy.py`
- `src/apex_fpl/optimisation/cvar.py`
- `src/apex_fpl/optimisation/exact_decision.py`
- `src/apex_fpl/optimisation/initial_horizon.py`
- `src/apex_fpl/optimisation/mechanics.py`
- `src/apex_fpl/optimisation/solver_status.py`
- `src/apex_fpl/optimisation/squad.py`
- `src/apex_fpl/optimisation/transfer_views.py`
- `src/apex_fpl/optimisation/transfers.py`
- `upstreams.lock.json`

## REIMPLEMENT_FROM_CONTRACT

Keep the requirement/lesson, rebuild from the constitutional V2 contract; do not preserve V1 orchestration as architecture.

- `data/manual/specialist_predictions.csv`
- `data/manual/squad_hierarchy.csv`
- `data/manual/tactical_roles.csv`
- `data/manual/tactical_roles.example.csv`
- `data/manual/transfer_checks.csv`
- `scripts/apply_joint_path_promotion.py`
- `scripts/apply_joint_path_promotion_rebased.py`
- `scripts/build_decision_bundle.py`
- `scripts/build_open_solver_parity_input.py`
- `scripts/export_airsenal.py`
- `scripts/export_open_solver.py`
- `scripts/finalize_production_status.py`
- `scripts/materialize_selection_reality_evidence.py`
- `scripts/promote_certified_generation.py`
- `scripts/run_adversarial_launch_ban.py`
- `scripts/run_airsenal_worker.py`
- `scripts/run_apex.py`
- `scripts/run_open_solver_parity.py`
- `src/apex_fpl/services/adversarial_certification.py`
- `src/apex_fpl/services/answer_context.py`
- `src/apex_fpl/services/audit_contracts.py`
- `src/apex_fpl/services/cached_launch.py`
- `src/apex_fpl/services/decision_eligibility.py`
- `src/apex_fpl/services/evidence_time.py`
- `src/apex_fpl/services/finalized_stability.py`
- `src/apex_fpl/services/hierarchy_evidence.py`
- `src/apex_fpl/services/integrity.py`
- `src/apex_fpl/services/joint_initial_path.py`
- `src/apex_fpl/services/open_solver_export.py`
- `src/apex_fpl/services/pinnacle_readiness.py`
- `src/apex_fpl/services/player_identity.py`
- `src/apex_fpl/services/player_truth.py`
- `src/apex_fpl/services/release_profile.py`
- `src/apex_fpl/services/selection_reality.py`
- `src/apex_fpl/services/selection_reality_evidence.py`
- `src/apex_fpl/services/specialist_disagreement.py`
- `src/apex_fpl/services/statistical_truth.py`
- `src/apex_fpl/services/strategy.py`
- `src/apex_fpl/services/team_state.py`
- `src/apex_fpl/services/transfer_intelligence.py`

## TEST_REFERENCE_ONLY

Keep as regression/oracle material and re-express against V2 contracts; V1 implementation is not production authority.

- `scripts/audit_bench_stress.py`
- `scripts/audit_inseason_action_sensitivity.py`
- `scripts/audit_max_ev_policy.py`
- `scripts/audit_player_identity.py`
- `scripts/audit_projection_truth.py`
- `scripts/audit_statistical_truth.py`
- `scripts/certify_adversarial_launch_ban.py`
- `scripts/certify_release_generation.py`
- `scripts/check_governance_consistency.py`
- `scripts/validate_fixture_fallback_selection.py`
- `tests/test_adversarial_certification.py`
- `tests/test_airsenal_source_absence_policy.py`
- `tests/test_airsenal_workflow_contract.py`
- `tests/test_architecture_hardening.py`
- `tests/test_audit_contracts.py`
- `tests/test_audit_player_identity_script.py`
- `tests/test_bench_policy.py`
- `tests/test_bench_stress_contract.py`
- `tests/test_build_decision_bundle_identity.py`
- `tests/test_cached_launch.py`
- `tests/test_certification_workflow_contract.py`
- `tests/test_core_refresh_workflow_contract.py`
- `tests/test_entry_state.py`
- `tests/test_evidence_eligibility.py`
- `tests/test_exact_decision.py`
- `tests/test_export_airsenal_identity.py`
- `tests/test_finalized_stability.py`
- `tests/test_fixture_elo.py`
- `tests/test_fpl_specialist_evidence_contract.py`
- `tests/test_hardened_convergence.py`
- `tests/test_inseason_action_sensitivity.py`
- `tests/test_inseason_answer_contract.py`
- `tests/test_integrity.py`
- `tests/test_joint_path_promotion.py`
- `tests/test_market_activation_contract.py`
- `tests/test_open_solver_export.py`
- `tests/test_personal_team_state_contract.py`
- `tests/test_pinnacle_readiness.py`
- `tests/test_pipeline.py`
- `tests/test_player_identity.py`
- `tests/test_production_publication_contract.py`
- `tests/test_release_fail_closed_contracts.py`
- `tests/test_release_failure_observability.py`
- `tests/test_release_generation_certificate.py`
- `tests/test_release_profile.py`
- `tests/test_release_workflow_contract.py`
- `tests/test_run_apex_identity_provenance.py`
- `tests/test_selection_reality.py`
- `tests/test_selection_reality_evidence.py`
- `tests/test_set_pieces.py`
- `tests/test_specialist_disagreement.py`
- `tests/test_specialist_presolve_eligibility.py`
- `tests/test_statistical_truth.py`
- `tests/test_strategy.py`
- `tests/test_tactical_overrides.py`
- `tests/test_team_goals.py`
- `tests/test_transfer_candidate_pool.py`
- `tests/test_transfer_intelligence.py`
- `tests/test_transfers.py`

## DOCUMENTATION_REFERENCE

Keep as historical evidence/design rationale and supersede with the V2 constitutional documentation.

- `docs/APEX_DATA_SOURCES.md`
- `docs/architecture_invariants.md`
- `docs/deadline_runtime_certification.md`
- `docs/evidence/airsenal_truth_coverage_contract_2026-08-22.md`
- `docs/evidence/executable_action_mechanics_contract_2026-08-22.md`
- `docs/evidence/fpl_specialist_evidence_policy_2026-08-18.md`
- `docs/evidence/release_certification_contract_2026-08-22.md`
- `docs/joint_path_production_promotion.md`
- `docs/player_identity_integrity.md`

## Slice 0 migration decisions

- The V1 `pinnacle.yml` direct commit/push of generated state to `main` is **not ported**.
- PR #66 compare-and-swap lessons are retained, but CAS belongs to the ReleaseRegistry current pointer rather than the Git branch.
- Existing fail-closed V1 recommendation assembly remains a temporary producer. `V1_ACTIONABLE` is deliberately not called V2 `CERTIFIED`.
- Manual evidence CSV semantics are reimplemented through future EvidenceLedger/OverrideLedger slices rather than becoming V2 authority.
- All PR #66 tests remain regression sources until their V2 equivalents exist.
