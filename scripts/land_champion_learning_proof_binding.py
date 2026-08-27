from pathlib import Path


def replace_block(path: str, start_marker: str, end_marker: str, replacement: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    start = text.find(start_marker)
    end = text.find(end_marker, start)
    if start < 0 or end < 0:
        raise SystemExit(f"{path}: block markers missing")
    p.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"{path}: expected one replacement target, found {text.count(old)}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Bind production empirical learning proofs to the exact champion learning chain.
path = "src/apex_fpl/control/production_cutover.py"
replace_once(
    path,
    "from apex_fpl.control.experiment_registry import load_empirical_qualification_certificate\n",
    "from apex_fpl.control.experiment_registry import load_empirical_qualification_certificate\nfrom apex_fpl.control.learning_promotion_replay import (\n    VerifiedForecastChampionEvidence,\n    verify_forecast_registry_champion,\n)\n",
)
replace_block(
    path,
    "def _bundle_empirical_bindings(\n",
    "\n\ndef _verified_bundle_for_release(\n",
    '''def _bundle_empirical_bindings(\n    verified: VerifiedProductionPlanningBundle | None,\n    *,\n    champion_evidence: VerifiedForecastChampionEvidence | None = None,\n) -> dict[str, _EmpiricalReleaseBinding]:\n    bindings: dict[str, _EmpiricalReleaseBinding] = {}\n    if verified is not None:\n        model = verified.forecast_model\n        policy = verified.decision_policy\n        report = verified.robustness_report\n        if model.qualification_artifact_id is None or policy.qualification_artifact_id is None:\n            raise ValueError("production bundle direct empirical subjects lack qualification artifacts")\n        bindings.update(\n            {\n                "PO-FORECAST-QUALIFICATION-001": _EmpiricalReleaseBinding(\n                    subject_id=qualification_subject_id(model.semantic_payload()),\n                    semantic_evidence_id=str(model.model_artifact_id),\n                    qualification_artifact_id=model.qualification_artifact_id,\n                ),\n                "PO-DECISION-POLICY-QUALIFICATION-001": _EmpiricalReleaseBinding(\n                    subject_id=qualification_subject_id(policy.semantic_payload()),\n                    semantic_evidence_id=str(policy.decision_policy_id),\n                    qualification_artifact_id=policy.qualification_artifact_id,\n                ),\n                "PO-SCENARIO-CONVERGENCE-001": _EmpiricalReleaseBinding(\n                    subject_id=qualification_subject_id(report.semantic_payload()),\n                    semantic_evidence_id=str(report.robustness_report_id),\n                ),\n            }\n        )\n    if champion_evidence is not None:\n        candidate_report = champion_evidence.promotion.candidate.report\n        promotion = champion_evidence.promotion.certificate\n        bindings.update(\n            {\n                "PO-MODEL-EVALUATION-001": _EmpiricalReleaseBinding(\n                    subject_id=qualification_subject_id(candidate_report.semantic_payload()),\n                    semantic_evidence_id=str(candidate_report.evaluation_id),\n                ),\n                "PO-MODEL-PROMOTION-001": _EmpiricalReleaseBinding(\n                    subject_id=qualification_subject_id(promotion.semantic_payload()),\n                    semantic_evidence_id=str(promotion.promotion_id),\n                ),\n            }\n        )\n    return bindings\n''',
)
replace_block(
    path,
    "    verified_bundle = _verified_bundle_for_release(\n",
    "    backend_artifacts = (\n",
    '''    verified_bundle = _verified_bundle_for_release(\n        bundle_id=bundle_id,\n        world_id=world_id,\n        season=season,\n        entry=entry,\n        gameweek=gameweek,\n        store=artifact_store,\n    )\n    manifest_id = _verify_artifact(\n        artifact_store, artifact_manifest_id, label="production artifact manifest"\n    )\n    champion_artifact_id: str | None = None\n    champion_evidence: VerifiedForecastChampionEvidence | None = None\n    if champion_generation_artifact_id is not None:\n        champion_artifact_id = _verify_artifact(\n            artifact_store,\n            champion_generation_artifact_id,\n            label="production champion generation",\n        )\n        if verified_bundle is None:\n            stored_champion = load_production_champion_generation(\n                champion_artifact_id,\n                as_of=created_at,\n                store=artifact_store,\n            )\n        else:\n            stored_champion = verify_bundle_champion_authority(\n                champion_artifact_id,\n                verified_bundle=verified_bundle,\n                as_of=created_at,\n                store=artifact_store,\n            )\n        champion_evidence = verify_forecast_registry_champion(\n            stored_champion.generation.forecast_registry_generation_artifact_id,\n            season=stored_champion.generation.season,\n            as_of=stored_champion.generation.authorized_at,\n            store=artifact_store,\n        )\n    empirical_bindings = _bundle_empirical_bindings(\n        verified_bundle,\n        champion_evidence=champion_evidence,\n    )\n    claim_artifacts = _claim_artifacts(\n        assurance_case,\n        obligations_tuple,\n        artifact_store,\n        season=season,\n        as_of=created_at,\n        empirical_bindings=empirical_bindings,\n        verified_bundle=verified_bundle,\n    )\n''',
)

# Make synthetic production claims certify the exact replayed learning evaluation/promotion.
path = "tests/test_v2_production_cutover.py"
replace_once(
    path,
    "from apex_fpl.control.experiment_registry import (\n",
    "from apex_fpl.control.champion_authority import verify_bundle_champion_authority\nfrom apex_fpl.control.experiment_registry import (\n",
)
replace_once(
    path,
    "from apex_fpl.control.production_cutover import (\n",
    "from apex_fpl.control.learning_promotion_replay import verify_forecast_registry_champion\nfrom apex_fpl.control.production_cutover import (\n",
)
replace_once(
    path,
    "from champion_authority_helpers import synthetic_production_champion_authority\n",
    "from champion_authority_helpers import synthetic_production_champion_authority\nfrom empirical_qualification_helpers import synthetic_supported_qualification_artifact\n",
)
replace_once(
    path,
    "from production_planning_bundle_helpers import (\n    DirectQualificationMaterial,\n    synthetic_production_planning_bundle,\n)\n",
    "from production_planning_bundle_helpers import (\n    DirectQualificationMaterial,\n    _qualification_material,\n    synthetic_production_planning_bundle,\n)\n",
)
replace_block(
    path,
    "def _case(\n",
    "\n\ndef _backend(\n",
    '''def _case(\n    store,\n    claim_artifact: str,\n    *,\n    missing: str | None = None,\n    inconclusive: str | None = None,\n    scope: str = SCOPE,\n    unrelated_learning_proof: str | None = None,\n) -> AssuranceCase:\n    fixture = _fixture(store)\n    authority = synthetic_production_champion_authority(\n        store=store,\n        fixture=fixture,\n        reviewed_at=CREATED_AT,\n    )\n    verified_bundle = load_production_planning_bundle(fixture.bundle.bundle_id, store=store)\n    verified_generation = verify_bundle_champion_authority(\n        authority.generation.artifact_id,\n        verified_bundle=verified_bundle,\n        as_of=CREATED_AT,\n        store=store,\n    )\n    learning = verify_forecast_registry_champion(\n        verified_generation.generation.forecast_registry_generation_artifact_id,\n        season=SEASON,\n        as_of=verified_generation.generation.authorized_at,\n        store=store,\n    )\n    direct = dict(fixture.direct_qualifications)\n    evaluation = learning.promotion.candidate.report\n    evaluation_qualification = synthetic_supported_qualification_artifact(\n        store=store,\n        subject_payload=evaluation.semantic_payload(),\n        subject_kind="apex.model-evaluation",\n        proof_id="PO-MODEL-EVALUATION-001",\n        season=SEASON,\n        valid_until=VALID_UNTIL,\n    )\n    direct["PO-MODEL-EVALUATION-001"] = _qualification_material(\n        store=store,\n        artifact_id=evaluation_qualification,\n        semantic_evidence_id=str(evaluation.evaluation_id),\n    )\n    promotion = learning.promotion.certificate\n    promotion_qualification = synthetic_supported_qualification_artifact(\n        store=store,\n        subject_payload=promotion.semantic_payload(),\n        subject_kind="apex.model-promotion",\n        proof_id="PO-MODEL-PROMOTION-001",\n        season=SEASON,\n        valid_until=VALID_UNTIL,\n    )\n    direct["PO-MODEL-PROMOTION-001"] = _qualification_material(\n        store=store,\n        artifact_id=promotion_qualification,\n        semantic_evidence_id=str(promotion.promotion_id),\n    )\n    parity = (\n        None\n        if missing == PARITY_PROOF_ID or inconclusive == PARITY_PROOF_ID\n        else synthetic_planning_parity_material(store=store, fixture=fixture)\n    )\n    claims = []\n    for proof_id in sorted(MANDATORY_PRODUCTION_PROOF_IDS):\n        if proof_id == missing:\n            continue\n        empirical = proof_id in EMPIRICAL_PRODUCTION_PROOF_IDS\n        artifact_ids = [claim_artifact]\n        evidence_ids = ["synthetic-evidence"]\n        if empirical and proof_id != inconclusive:\n            if proof_id in direct and proof_id != unrelated_learning_proof:\n                qualification_artifact, subject_id, experiment_id, semantic_id = (\n                    _direct_claim_evidence(direct[proof_id])\n                )\n                artifact_ids.append(qualification_artifact)\n                evidence_ids.extend((subject_id, experiment_id, semantic_id))\n            else:\n                qualification_artifact, subject_id, experiment_id = _empirical_qualification(\n                    store,\n                    proof_id,\n                )\n                artifact_ids.append(qualification_artifact)\n                evidence_ids.extend((subject_id, experiment_id))\n        if proof_id == PARITY_PROOF_ID and proof_id != inconclusive:\n            assert parity is not None\n            artifact_ids.extend(parity.artifact_ids)\n            evidence_ids.extend(parity.evidence_ids)\n        claims.append(\n            AssuranceClaim(\n                proof_id=proof_id,\n                status=(\n                    ProofStatus.INCONCLUSIVE\n                    if proof_id == inconclusive\n                    else ProofStatus.SUPPORTED\n                    if empirical\n                    else ProofStatus.PROVEN\n                ),\n                evidence_ids=tuple(evidence_ids),\n                test_ids=("synthetic-test",),\n                artifact_ids=tuple(artifact_ids),\n            )\n        )\n    return AssuranceCase(release_scope=scope, claims=tuple(claims))\n''',
)
replace_once(
    path,
    "from apex_fpl.control.production_cutover import (\n    execute_production_cutover,\n    load_production_cutover_report,\n)\n",
    "from apex_fpl.control.production_cutover import (\n    execute_production_cutover,\n    load_production_cutover_report,\n)\nfrom apex_fpl.control.production_planning_bundle import load_production_planning_bundle\n",
)
insert_marker = "\ndef test_legacy_v1_bundle_is_rejected_before_pointer_write(tmp_path: Path) -> None:\n"
negative_tests = '''\n\n@pytest.mark.parametrize(\n    "proof_id",\n    ("PO-MODEL-EVALUATION-001", "PO-MODEL-PROMOTION-001"),\n)\ndef test_unrelated_valid_learning_empirical_proof_cannot_authorize_champion_chain(\n    tmp_path: Path,\n    proof_id: str,\n) -> None:\n    store = _DurableArtifactStore(tmp_path / "artifacts")\n    registry = _DurableReleaseRegistry(tmp_path / "production")\n    claim_artifact = _artifact(store, "claim")\n    case = _case(\n        store,\n        claim_artifact,\n        unrelated_learning_proof=proof_id,\n    )\n    with pytest.raises(ValueError, match=rf"matching typed qualification evidence: {proof_id}"):\n        _execute(\n            tmp_path,\n            case=case,\n            store=store,\n            registry=registry,\n        )\n    assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None\n'''
p = Path(path)
text = p.read_text(encoding="utf-8")
if negative_tests.strip() not in text:
    if text.count(insert_marker) != 1:
        raise SystemExit("production cutover negative-test insertion marker mismatch")
    text = text.replace(insert_marker, negative_tests + insert_marker, 1)
    p.write_text(text, encoding="utf-8")

print("champion learning empirical proof binding patched")
