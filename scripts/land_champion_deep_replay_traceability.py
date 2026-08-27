from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one target, found {count}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def insert_once(path: str, marker: str, insertion: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if insertion in text:
        return
    count = text.count(marker)
    if count != 1:
        raise SystemExit(f"{path}: expected one insertion marker, found {count}")
    p.write_text(text.replace(marker, insertion + marker, 1), encoding="utf-8")


# Keep the forged-promotion regression on a valid parent-linked transition so the deep
# evaluator/promotion replay, rather than the bootstrap guard, rejects it.
path = "tests/test_v2_champion_authority.py"
old = '''    forged_registry = ModelRegistryGeneration(\n        season=fixture.bundle.season,\n        generation=1,\n        parent_generation_id=None,\n        registered_model_ids=(candidate_model_id, incumbent_model_id),\n        champion_model_id=candidate_model_id,\n        promotion_id=forged.promotion_id,\n        source_artifact_ids=(forged_artifact,),\n    )\n    forged_registry_artifact = store_learning_object(\n        forged_registry,\n        store=store,\n    ).artifact_id\n'''
new = '''    bootstrap = ModelRegistryGeneration(\n        season=fixture.bundle.season,\n        generation=1,\n        parent_generation_id=None,\n        registered_model_ids=(candidate_model_id, incumbent_model_id),\n        champion_model_id=None,\n        promotion_id=None,\n        source_artifact_ids=(store.put_bytes(b"forged registry bootstrap").artifact_id,),\n    )\n    bootstrap_artifact = store_learning_object(bootstrap, store=store).artifact_id\n    forged_registry = ModelRegistryGeneration(\n        season=fixture.bundle.season,\n        generation=2,\n        parent_generation_id=bootstrap.generation_id,\n        registered_model_ids=(candidate_model_id, incumbent_model_id),\n        champion_model_id=candidate_model_id,\n        promotion_id=forged.promotion_id,\n        source_artifact_ids=(forged_artifact,),\n    )\n    forged_registry_artifact = store_learning_object(\n        forged_registry,\n        store=store,\n        parent_artifact_ids=(bootstrap_artifact,),\n    ).artifact_id\n'''
replace_once(path, old, new)

# Static traceability must name the full registry/evaluator replay now in force.
path = "tests/test_v2_production_traceability.py"
replace_once(
    path,
    '    assert "verify_model_promotion_replay(" in champion\n    assert "registry.verify_policy(" in promotion\n    assert "production=True" in promotion\n',
    '    assert "verify_forecast_registry_champion(" in champion\n    assert "verify_model_evaluation_replay(" in promotion\n    assert "evaluate_model(" in promotion\n    assert "apply_model_promotion(" in promotion\n    assert "registry.verify_policy(" in promotion\n    assert "production=True" in promotion\n',
)
replace_once(
    path,
    '    assert "PlanningReferenceSolverCertificateId" in set(proof["required_evidence"])\n',
    '    assert "PlanningReferenceSolverCertificateId" in set(proof["required_evidence"])\n    assert "ProductionChampionGeneration" in set(proof["required_evidence"])\n    assert "ModelRegistryGenerationId" in set(proof["required_evidence"])\n    assert "ModelPromotionId" in set(proof["required_evidence"])\n    assert "ModelEvaluationId" in set(proof["required_evidence"])\n',
)

# Constitutional cutover proof explicitly owns the champion/evaluation/promotion replay.
path = "config/proof_obligations.yaml"
old_claim = "    claim: 'The exact executing production-control-plane build is pre-certified to enforce the V2 cutover mechanism: only a complete blocker-free constitutional AssuranceCase may create proof-derived publication authorization; every mandatory proof retains its pinned ProofClass; one content-addressed schema-v2 ProductionPlanningBundle must replay the exact current ManagerState, RuleSet, Forecast/model, qualified receding-horizon DecisionPolicy and support artifacts, FULL_OFFICIAL CandidateUniverse, complete zero-gap RecedingHorizonDecisionResult, ScenarioSet and converged RobustnessReport used by the release; the mandatory reference-solver proof must bind that exact PlanningResultId to a replay-valid planning-v2 qualified champion authorization/certificate with exact objective, root-action and trajectory parity; satisfying empirical claims are bound to the exact bundle-derived subjects; backend qualification is bound to actual non-reference durable shared identities; validity is explicit and time-bounded; publication uses stale-writer-safe CAS of one immutable PUBLISHED ReleaseRecord; and forged, stale, expired, corrupt, tactical-v1, legacy schema-v1, shadow, CERTIFIED-only, random-artifact, unrelated-qualification, unqualified-solver or reference-filesystem states remain non-authoritative.'\n"
new_claim = "    claim: 'The exact executing production-control-plane build is pre-certified to enforce the V2 cutover mechanism: only a complete blocker-free constitutional AssuranceCase may create proof-derived publication authorization; every mandatory proof retains its pinned ProofClass; one content-addressed schema-v2 ProductionPlanningBundle must replay the exact current ManagerState, RuleSet, Forecast/model, qualified receding-horizon DecisionPolicy and support artifacts, FULL_OFFICIAL CandidateUniverse, complete zero-gap RecedingHorizonDecisionResult, ScenarioSet and converged RobustnessReport used by the release; one immutable point-in-time ProductionChampionGeneration must exact-match that bundle and replay a parent-linked ModelRegistryGeneration whose exact training, evaluation dataset, observations, OutcomeTruthRegistry, champion LearningPolicyRegistry, candidate/incumbent ModelEvaluationReports, comparison and ModelPromotionCertificate independently re-derive the selected forecast champion, while reviewed non-model admissions replay at authorization time; PO-MODEL-EVALUATION-001 and PO-MODEL-PROMOTION-001 must qualify those exact replay-derived learning subjects rather than unrelated valid evidence; the mandatory reference-solver proof must bind the exact PlanningResultId to a replay-valid planning-v2 qualified champion authorization/certificate with exact objective, root-action and trajectory parity; backend qualification is bound to actual non-reference durable shared identities; validity is explicit and time-bounded; publication uses stale-writer-safe CAS of one immutable PUBLISHED ReleaseRecord; and forged, stale, expired, corrupt, tactical-v1, legacy schema-v1, shadow, CERTIFIED-only, random-artifact, unrelated-qualification, unqualified-solver or reference-filesystem states remain non-authoritative.'\n"
replace_once(path, old_claim, new_claim)
replace_once(
    path,
    "    required_evidence: [BuildManifest, source_sha, runtime_digest, immutable_CI_test_evidence, ProductionPlanningBundle, ManagerStateId, RuleSetId, DecisionPolicyId, ModelArtifactId, CandidateUniverseId, PlanningResultId, PlanningReferenceSolverCertificateId, ReferenceSolverAuthorizationId, RobustnessReportId, production_planning_bundle_replay_test_results, planning_reference_solver_contract_test_results, empirical_qualification_contract_test_results, backend_binding_test_results, authority_validity_test_results]\n",
    "    required_evidence: [BuildManifest, source_sha, runtime_digest, immutable_CI_test_evidence, ProductionPlanningBundle, ProductionChampionGeneration, ModelRegistryGenerationId, ModelPromotionId, ModelEvaluationId, ChampionAdmissionCertificate, ManagerStateId, RuleSetId, DecisionPolicyId, ModelArtifactId, CandidateUniverseId, PlanningResultId, PlanningReferenceSolverCertificateId, ReferenceSolverAuthorizationId, RobustnessReportId, production_planning_bundle_replay_test_results, champion_authority_replay_test_results, truth_governed_learning_replay_test_results, planning_reference_solver_contract_test_results, empirical_qualification_contract_test_results, backend_binding_test_results, authority_validity_test_results]\n",
)
old_tests = "    required_tests: [test_production_cutover_publishes_only_after_complete_pass_and_exact_cas, test_schema_v2_planning_bundle_round_trip_replays_exact_lineage, test_legacy_v1_bundle_is_rejected_before_pointer_write, test_production_cutover_requires_schema_v2_planning_bundle_authority, test_production_reference_solver_proof_is_planning_bound_and_replay_validated, test_random_artifact_cannot_satisfy_reference_solver_parity, test_planning_parity_certificate_without_champion_authorization_is_rejected, test_direct_policy_qualification_cannot_authorize_different_bundle_policy, test_incomplete_constitutional_proof_surface_is_rejected_before_pointer_write, test_proof_class_laundering_is_rejected_before_pointer_write, test_random_artifact_cannot_satisfy_empirical_production_proof, test_missing_required_proof_withholds_and_never_moves_production_pointer, test_unqualified_backend_withholds_even_when_release_certificate_passes, test_reference_filesystem_backends_cannot_be_qualified_by_green_booleans, test_backend_qualification_must_match_actual_adapter_identities, test_missing_or_invalid_validity_horizon_withholds, test_stale_writer_fails_closed_and_cannot_become_current, test_forged_published_ready_record_without_authorization_is_rejected, test_v1_and_certified_records_cannot_become_v2_answer_authority, test_corrupt_publication_authorization_withholds_current_answer, test_corrupt_production_bundle_withholds_current_answer, test_expired_current_release_is_non_actionable_even_when_pointer_is_current, test_publication_authorization_validity_must_match_release_record, test_authorization_cannot_be_replayed_through_different_backend_identities, test_answer_authority_withholds_if_current_pointer_changes_during_verification, test_production_cutover_accepts_no_independent_readiness_or_safety_input, test_answer_authority_is_current_published_v2_only, test_answer_authority_requires_explicit_replayable_time_and_no_hidden_clock, test_cutover_and_answer_authority_both_replay_exact_production_bundle, test_production_proof_class_contract_exactly_matches_required_yaml, test_qualification_subject_identity_ignores_only_qualification_attachment, test_experiment_must_be_predeclared_before_evaluation_window]\n"
new_tests = "    required_tests: [test_production_cutover_publishes_only_after_complete_pass_and_exact_cas, test_champion_authority_replays_all_four_bundle_champions, test_forecast_champion_rejects_hand_authored_promote_certificate, test_truth_governed_promoted_registry_replays_full_evaluation_and_cas_chain, test_structurally_valid_complete_evaluation_without_truth_inputs_cannot_be_replayed, test_unrelated_valid_learning_empirical_proof_cannot_authorize_champion_chain, test_schema_v2_planning_bundle_round_trip_replays_exact_lineage, test_legacy_v1_bundle_is_rejected_before_pointer_write, test_production_cutover_requires_schema_v2_planning_bundle_authority, test_production_reference_solver_proof_is_planning_bound_and_replay_validated, test_random_artifact_cannot_satisfy_reference_solver_parity, test_planning_parity_certificate_without_champion_authorization_is_rejected, test_direct_policy_qualification_cannot_authorize_different_bundle_policy, test_incomplete_constitutional_proof_surface_is_rejected_before_pointer_write, test_proof_class_laundering_is_rejected_before_pointer_write, test_random_artifact_cannot_satisfy_empirical_production_proof, test_missing_required_proof_withholds_and_never_moves_production_pointer, test_unqualified_backend_withholds_even_when_release_certificate_passes, test_reference_filesystem_backends_cannot_be_qualified_by_green_booleans, test_backend_qualification_must_match_actual_adapter_identities, test_missing_or_invalid_validity_horizon_withholds, test_stale_writer_fails_closed_and_cannot_become_current, test_forged_published_ready_record_without_authorization_is_rejected, test_v1_and_certified_records_cannot_become_v2_answer_authority, test_corrupt_publication_authorization_withholds_current_answer, test_corrupt_production_bundle_withholds_current_answer, test_expired_current_release_is_non_actionable_even_when_pointer_is_current, test_publication_authorization_validity_must_match_release_record, test_authorization_cannot_be_replayed_through_different_backend_identities, test_answer_authority_withholds_if_current_pointer_changes_during_verification, test_production_cutover_accepts_no_independent_readiness_or_safety_input, test_answer_authority_is_current_published_v2_only, test_answer_authority_requires_explicit_replayable_time_and_no_hidden_clock, test_cutover_and_answer_authority_both_replay_exact_production_bundle, test_cutover_and_answer_authority_both_replay_exact_champion_authority, test_production_proof_class_contract_exactly_matches_required_yaml, test_qualification_subject_identity_ignores_only_qualification_attachment, test_experiment_must_be_predeclared_before_evaluation_window]\n"
replace_once(path, old_tests, new_tests)

# Production requirement owns the new replay regression file too.
path = "config/requirements.yaml"
replace_once(
    path,
    "tests/test_v2_champion_authority.py, tests/test_v2_production_cutover.py",
    "tests/test_v2_champion_authority.py, tests/test_v2_learning_promotion_replay.py, tests/test_v2_production_cutover.py",
)

# Focused CI and Shadow path coverage.
path = ".github/workflows/apex.yml"
replace_once(
    path,
    "          tests/test_v2_champion_authority.py\n          tests/test_v2_production_cutover.py\n",
    "          tests/test_v2_champion_authority.py\n          tests/test_v2_learning_promotion_replay.py\n          tests/test_v2_production_cutover.py\n",
)
# The same pair appears in Ruff later; replace the remaining occurrence.
replace_once(
    path,
    "          tests/test_v2_champion_authority.py\n          tests/test_v2_production_cutover.py\n",
    "          tests/test_v2_champion_authority.py\n          tests/test_v2_learning_promotion_replay.py\n          tests/test_v2_production_cutover.py\n",
)
path = ".github/workflows/v2-shadow-production.yml"
replace_once(
    path,
    '      - "tests/test_v2_champion_authority.py"\n',
    '      - "tests/test_v2_champion_authority.py"\n      - "tests/test_v2_learning_promotion_replay.py"\n',
)

# Design documentation names the deeper truth replay explicitly.
path = "docs/APEX_CHAMPION_AUTHORITY_V2.md"
replace_once(
    path,
    "It reconstructs those typed objects, reconciles their semantic identities and common-truth lineage, checks the comparison rows against the retained evaluation metrics, replays the learning policy at the generation authorization time, and re-runs the existing promotion threshold/interval logic.",
    "It reconstructs the retained training run, evaluation dataset/cases, normalized observations, OutcomeTruthRegistry, learning policy and champion LearningPolicyRegistry; re-runs `evaluate_model(production=True)` for candidate and incumbent; reconciles their semantic identities and common-truth lineage; re-runs the exact comparison; replays the learning policy at the generation authorization time; and re-runs the existing promotion threshold/interval logic plus the parent-linked `apply_model_promotion` registry transition.",
)

print("deep champion replay traceability patched")
