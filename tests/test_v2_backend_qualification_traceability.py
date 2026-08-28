from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "src" / "apex_fpl" / "core" / "backend_qualification.py"
OPERATIONAL = ROOT / "src" / "apex_fpl" / "control" / "backend_operational_qualification.py"
CUTOVER = ROOT / "src" / "apex_fpl" / "control" / "production_cutover.py"
CUTOVER_TRANSACTION = ROOT / "src" / "apex_fpl" / "control" / "_production_cutover_legacy.py"
VERIFIER = ROOT / "src" / "apex_fpl" / "control" / "production_authority_verification.py"
AUTHORITY = ROOT / "src" / "apex_fpl" / "control" / "production_authority.py"
LOADER = ROOT / "src" / "apex_fpl" / "control" / "production_backend_qualification.py"
DOC = ROOT / "docs" / "APEX_BACKEND_OPERATIONAL_QUALIFICATION_V2.md"
ARTIFACT_DOC = ROOT / "docs" / "APEX_ARTIFACT_STORE.md"
INVARIANTS = ROOT / "docs" / "APEX_INVARIANTS.md"
REQUIREMENTS = ROOT / "config" / "requirements.yaml"


def test_backend_production_qualification_is_structurally_two_plane() -> None:
    core = CORE.read_text(encoding="utf-8")
    operational = OPERATIONAL.read_text(encoding="utf-8")

    for evidence_kind in (
        "RETENTION",
        "ACCESS_CONTROL",
        "CREDENTIAL_SEPARATION",
        "BACKUP",
        "RESTORE",
        "DISASTER_RECOVERY",
        "AVAILABILITY",
        "GEOGRAPHIC_DURABILITY",
    ):
        assert evidence_kind in core

    assert "class VerifiedBackendMechanicalQualification" in operational
    assert "class VerifiedBackendQualification" in operational
    assert "derive_backend_qualification_from_probes" in operational
    assert "derive_production_backend_qualification" in operational
    assert "BackendDeploymentQualificationEvidence" in operational
    assert "environment_class == \"PRODUCTION\"" in core
    assert "deployment.supported" in operational
    assert "apex-backend-production-qualification-binding" in operational
    assert "backend qualification bindings do not share deployment evidence" in operational


def test_cutover_and_replay_both_require_replayed_backend_qualification() -> None:
    cutover = CUTOVER.read_text(encoding="utf-8")
    transaction = CUTOVER_TRANSACTION.read_text(encoding="utf-8")
    verifier = VERIFIER.read_text(encoding="utf-8")
    loader = LOADER.read_text(encoding="utf-8")
    operational = OPERATIONAL.read_text(encoding="utf-8")

    assert "verify_production_authority_closure(" in cutover
    assert "_legacy.execute_production_cutover(" in cutover
    assert "verify_backend_qualification_evidence(" in transaction
    assert "verify_stored_backend_qualification_evidence(" in transaction
    assert "_replay_backend_qualification(" in verifier
    assert "verify_stored_backend_qualification_evidence(" in loader
    assert "artifact-store probe evidence belongs to a different backend" in operational
    assert "deployment evidence belongs to a different ArtifactStore backend" in operational
    assert "deployment evidence belongs to a different ReleaseRegistry backend" in operational


def test_runtime_publication_paths_cannot_self_author_plane_b_evidence() -> None:
    forbidden = (
        "store_backend_deployment_evidence_item",
        "store_backend_deployment_qualification_evidence",
        "derive_production_backend_qualification",
    )
    for path in (CUTOVER, VERIFIER, AUTHORITY, LOADER):
        text = path.read_text(encoding="utf-8")
        for symbol in forbidden:
            assert symbol not in text

    for source in (ROOT / "src" / "apex_fpl").rglob("*.py"):
        if source == OPERATIONAL:
            continue
        text = source.read_text(encoding="utf-8")
        assert "store_backend_deployment_evidence_item(" not in text
        assert "store_backend_deployment_qualification_evidence(" not in text


def test_ci_postgres_and_synthetic_fixtures_are_never_documented_as_real_evidence() -> None:
    qualification_doc = DOC.read_text(encoding="utf-8")
    artifact_doc = ARTIFACT_DOC.read_text(encoding="utf-8")
    combined = qualification_doc + "\n" + artifact_doc

    assert "GitHub Actions" in combined
    assert "mechanism" in combined
    assert "real production" in combined.lower()
    assert "Synthetic test fixtures" in qualification_doc

    for source in (ROOT / "src" / "apex_fpl").rglob("*.py"):
        assert "synthetic_production_backend_qualification" not in source.read_text(
            encoding="utf-8"
        )


def test_existing_constitutional_backend_hook_remains_traceable() -> None:
    invariants = INVARIANTS.read_text(encoding="utf-8")
    requirements = REQUIREMENTS.read_text(encoding="utf-8")

    assert "INV-PRODUCTION-BACKEND-QUALIFIED" in invariants
    assert "INV-PRODUCTION-BACKEND-QUALIFIED" in requirements
    assert "REQ-V2-PRODUCTION-CUTOVER" in requirements
    assert "src/apex_fpl/control/production_backend_qualification.py" in requirements
    assert "tests/test_v2_production_cutover.py" in requirements
    assert "tests/test_v2_production_authority.py" in requirements
