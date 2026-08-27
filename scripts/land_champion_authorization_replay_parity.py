from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one target, found {count}: {old[:160]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Stored publication authorization replay must bind the same exact champion learning
# evaluation/promotion subjects as issuance.  Replaying only the champion generation but
# dropping its derived empirical bindings would make post-publication verification weaker.
path = "src/apex_fpl/control/production_cutover.py"
old = '''    empirical_bindings = _bundle_empirical_bindings(verified_bundle)\n    if authorization.champion_generation_artifact_id is not None:\n        if verified_bundle is None:\n            load_production_champion_generation(\n                authorization.champion_generation_artifact_id,\n                as_of=authorization.created_at,\n                store=artifact_store,\n            )\n        else:\n            verify_bundle_champion_authority(\n                authorization.champion_generation_artifact_id,\n                verified_bundle=verified_bundle,\n                as_of=authorization.created_at,\n                store=artifact_store,\n            )\n'''
new = '''    champion_evidence: VerifiedForecastChampionEvidence | None = None\n    if authorization.champion_generation_artifact_id is not None:\n        if verified_bundle is None:\n            stored_champion = load_production_champion_generation(\n                authorization.champion_generation_artifact_id,\n                as_of=authorization.created_at,\n                store=artifact_store,\n            )\n        else:\n            stored_champion = verify_bundle_champion_authority(\n                authorization.champion_generation_artifact_id,\n                verified_bundle=verified_bundle,\n                as_of=authorization.created_at,\n                store=artifact_store,\n            )\n        champion_evidence = verify_forecast_registry_champion(\n            stored_champion.generation.forecast_registry_generation_artifact_id,\n            season=stored_champion.generation.season,\n            as_of=stored_champion.generation.authorized_at,\n            store=artifact_store,\n        )\n    empirical_bindings = _bundle_empirical_bindings(\n        verified_bundle,\n        champion_evidence=champion_evidence,\n    )\n'''
replace_once(path, old, new)

# Regression: construct a structurally valid stored authorization around a different valid
# model-evaluation/model-promotion empirical certificate. Issuance is not involved in the
# replay under test, so this directly proves replay parity.
path = "tests/test_v2_production_cutover.py"
replace_once(
    path,
    "from __future__ import annotations\n\nfrom pathlib import Path\n",
    "from __future__ import annotations\n\nfrom dataclasses import replace\nfrom pathlib import Path\n",
)
replace_once(
    path,
    "from apex_fpl.control.production_cutover import (\n    execute_production_cutover,\n    load_production_cutover_report,\n)\n",
    "from apex_fpl.control.production_cutover import (\n    _seal_release_policy,\n    execute_production_cutover,\n    load_production_cutover_report,\n    load_production_publication_authorization,\n)\n",
)
replace_once(
    path,
    "from apex_fpl.core.experiments import (\n",
    "from apex_fpl.core.canonical import canonical_json_bytes\nfrom apex_fpl.core.experiments import (\n",
)
marker = "def test_legacy_v1_bundle_is_rejected_before_pointer_write(tmp_path: Path) -> None:\n"
test = '''@pytest.mark.parametrize(\n    "proof_id",\n    ("PO-MODEL-EVALUATION-001", "PO-MODEL-PROMOTION-001"),\n)\ndef test_stored_authorization_replay_rejects_unrelated_valid_learning_proof(\n    tmp_path: Path,\n    proof_id: str,\n) -> None:\n    store = _DurableArtifactStore(tmp_path / "artifacts")\n    registry = _DurableReleaseRegistry(tmp_path / "production")\n    _, _, outcome = _execute(\n        tmp_path,\n        store=store,\n        registry=registry,\n    )\n    authorization_artifact_id = (\n        outcome.release_record.publication_authorization_artifact_id\n    )\n    assert authorization_artifact_id is not None\n    authorization = load_production_publication_authorization(\n        authorization_artifact_id,\n        artifact_store=store,\n    )\n\n    unrelated_case = _case(\n        store,\n        _artifact(store, f"replay-unrelated-claim:{proof_id}"),\n        unrelated_learning_proof=proof_id,\n    )\n    case_artifact_id, proof_artifact_id = _seal_release_policy(\n        unrelated_case,\n        _obligations(),\n        store=store,\n    )\n    forged = replace(\n        authorization,\n        assurance_case_id=unrelated_case.case_id,\n        assurance_case_artifact_id=case_artifact_id,\n        proof_obligations_artifact_id=proof_artifact_id,\n    )\n    forged_ref = store.put_bytes(\n        canonical_json_bytes(\n            {\n                "schema_name": "apex-stored-production-publication-authorization",\n                "schema_version": 1,\n                "authorization_id": forged.authorization_id,\n                "payload": forged.semantic_payload(),\n            }\n        ),\n        media_type="application/json",\n        schema_name="apex-stored-production-publication-authorization",\n        schema_version="1",\n    )\n\n    with pytest.raises(\n        ValueError,\n        match=rf"matching typed qualification evidence: {proof_id}",\n    ):\n        load_production_publication_authorization(\n            forged_ref.artifact_id,\n            artifact_store=store,\n        )\n\n\n'''
p = Path(path)
text = p.read_text(encoding="utf-8")
if test.strip() not in text:
    if text.count(marker) != 1:
        raise SystemExit("production cutover replay regression insertion marker mismatch")
    p.write_text(text.replace(marker, test + marker, 1), encoding="utf-8")

# Constitutional cutover proof owns the replay-parity regression as required evidence.
path = "config/proof_obligations.yaml"
replace_once(
    path,
    "test_unrelated_valid_learning_empirical_proof_cannot_authorize_champion_chain, test_schema_v2_planning_bundle_round_trip_replays_exact_lineage",
    "test_unrelated_valid_learning_empirical_proof_cannot_authorize_champion_chain, test_stored_authorization_replay_rejects_unrelated_valid_learning_proof, test_schema_v2_planning_bundle_round_trip_replays_exact_lineage",
)

# Keep the design record explicit that issuance and replay use the same derived bindings.
path = "docs/APEX_CHAMPION_AUTHORITY_V2.md"
needle = "The production publication authorization stores the exact champion-generation artifact ID, and answer-authority replay verifies it again before a release may be considered current.\n"
replacement = needle + "Stored publication-authorization replay re-derives the same forecast champion learning evidence used at issuance and rebuilds the exact model-evaluation/model-promotion empirical bindings; a valid but unrelated learning qualification is rejected both before publication and during later authority replay.\n"
replace_once(path, needle, replacement)

print("champion authorization replay parity patched")
