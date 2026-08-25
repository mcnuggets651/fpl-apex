from __future__ import annotations

from pathlib import Path

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.experiment_registry import (
    ExperimentRegistration,
    ExperimentRegistry,
    derive_empirical_qualification_certificate,
    store_empirical_qualification_certificate,
    store_experiment_definition,
    store_experiment_registry,
    store_experiment_result,
)
from apex_fpl.control.production_authority import resolve_production_answer_authority
from apex_fpl.control.production_cutover import execute_production_cutover
from apex_fpl.control.release_registry import (
    FileSystemReleaseRegistry,
    ReleaseKey,
    ReleaseRecord,
    ReleaseStatus,
)
from apex_fpl.core.experiments import (
    ExactQualificationValue,
    ExperimentDefinition,
    ExperimentResult,
    QualificationMetricDirection,
    QualificationMetricResult,
    QualificationMetricRule,
)
from apex_fpl.core.ids import BundleId
from apex_fpl.core.production import MANDATORY_PRODUCTION_PROOF_IDS, ProductionBackendQualification
from apex_fpl.core.production_authority import ProductionAuthorityStatus
from apex_fpl.core.production_proof_contract import (
    EMPIRICAL_PRODUCTION_PROOF_IDS,
    PRODUCTION_EMPIRICAL_SUBJECT_KIND,
    PRODUCTION_PROOF_CLASSES,
)
from apex_fpl.core.proofs import (
    AssuranceCase,
    AssuranceClaim,
    ProofObligation,
    ProofStatus,
    ReleasePolicy,
)

from production_planning_bundle_helpers import synthetic_production_planning_bundle


SEASON = "2026-2027"
ENTRY = 63984
GAMEWEEK = 2
SCOPE = f"{SEASON}:{ENTRY}:{GAMEWEEK}:production"
CREATED_AT = "2026-08-25T06:00:00Z"
VALID_UNTIL = "2026-08-29T10:00:00Z"
AS_OF = "2026-08-25T07:00:00Z"


class _DurableArtifactStore:
    backend_id = "test.production.durable-artifact-store.v1"

    def __init__(self, root: Path):
        self.delegate = FileSystemArtifactStore(root)

    def put_bytes(self, content: bytes, **kwargs):
        return self.delegate.put_bytes(content, **kwargs)

    def read_bytes(self, artifact_id: str) -> bytes:
        return self.delegate.read_bytes(artifact_id)

    def verify(self, artifact_id: str) -> bool:
        return self.delegate.verify(artifact_id)


class _DurableReleaseRegistry:
    backend_id = "test.production.durable-release-registry.v1"

    def __init__(self, root: Path):
        self.delegate = FileSystemReleaseRegistry(root)

    def append(self, record):
        return self.delegate.append(record)

    def read_release(self, release_id: str):
        return self.delegate.read_release(release_id)

    def current_release_id(self, key: ReleaseKey) -> str | None:
        return self.delegate.current_release_id(key)

    def compare_and_swap_current(
        self,
        key: ReleaseKey,
        *,
        expected_release_id: str | None,
        new_release_id: str,
    ) -> None:
        self.delegate.compare_and_swap_current(
            key,
            expected_release_id=expected_release_id,
            new_release_id=new_release_id,
        )


def _artifact(store, text: str) -> str:
    return store.put_bytes(text.encode("utf-8")).artifact_id


def _empirical_qualification(store, proof_id: str) -> tuple[str, str, str]:
    """Build synthetic mechanism evidence; never a real production qualification."""

    subject_id = f"synthetic-authority-subject:{proof_id}"
    evaluator_artifact_id = _artifact(store, f"evaluator:{proof_id}")
    policy_artifact_id = _artifact(store, f"policy:{proof_id}")
    source_artifact_id = _artifact(store, f"source:{proof_id}")
    definition = ExperimentDefinition(
        proof_id=proof_id,
        subject_kind=PRODUCTION_EMPIRICAL_SUBJECT_KIND[proof_id],
        subject_id=subject_id,
        season=SEASON,
        evaluator_artifact_id=evaluator_artifact_id,
        policy_artifact_id=policy_artifact_id,
        declared_at="2026-08-01T00:00:00Z",
        evaluation_window_start="2026-08-02T00:00:00Z",
        evaluation_window_end="2026-08-24T00:00:00Z",
        minimum_sample_size=10,
        metric_rules=(
            QualificationMetricRule(
                metric_id="synthetic-score",
                direction=QualificationMetricDirection.AT_LEAST,
                threshold=ExactQualificationValue(1, 2),
            ),
        ),
        valid_until=VALID_UNTIL,
    )
    definition_ref = store_experiment_definition(definition, store=store)
    result = ExperimentResult(
        experiment_id=definition.experiment_id,
        proof_id=proof_id,
        subject_kind=definition.subject_kind,
        subject_id=subject_id,
        season=SEASON,
        evaluator_artifact_id=evaluator_artifact_id,
        evaluated_at="2026-08-24T00:00:00Z",
        sample_size=10,
        metrics=(
            QualificationMetricResult(
                metric_id="synthetic-score",
                value=ExactQualificationValue(1, 2),
            ),
        ),
        source_artifact_ids=(source_artifact_id,),
    )
    result_ref = store_experiment_result(result, store=store)
    experiment_registry = ExperimentRegistry(
        season=SEASON,
        registrations=(
            ExperimentRegistration(
                experiment_id=definition.experiment_id,
                definition_artifact_id=definition_ref.artifact_id,
            ),
        ),
    )
    registry_ref = store_experiment_registry(experiment_registry, store=store)
    certificate = derive_empirical_qualification_certificate(
        definition_artifact_id=definition_ref.artifact_id,
        result_artifact_id=result_ref.artifact_id,
        registry_artifact_id=registry_ref.artifact_id,
        store=store,
    )
    certificate_ref = store_empirical_qualification_certificate(certificate, store=store)
    assert certificate.supported is True
    return certificate_ref.artifact_id, subject_id, definition.experiment_id


def _qualified_cutover(tmp_path: Path):
    store = _DurableArtifactStore(tmp_path / "artifacts")
    registry = _DurableReleaseRegistry(tmp_path / "production")
    fixture = synthetic_production_planning_bundle(
        store=store,
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
    )
    evidence = _artifact(store, "proof-evidence")
    manifest = _artifact(store, "manifest")
    store_q = _artifact(store, "store-qualified")
    registry_q = _artifact(store, "registry-qualified")
    obligations = tuple(
        ProofObligation(
            proof_id=proof_id,
            claim=f"pre-publication mechanism proof {proof_id}",
            proof_class=PRODUCTION_PROOF_CLASSES[proof_id],
            scope="production-test",
            required_evidence=("artifact",),
            required_tests=("test",),
            failure_consequence="withhold",
            release_policy=ReleasePolicy.REQUIRED,
            owner="tests",
        )
        for proof_id in sorted(MANDATORY_PRODUCTION_PROOF_IDS)
    )
    claims: list[AssuranceClaim] = []
    for proof_id in sorted(MANDATORY_PRODUCTION_PROOF_IDS):
        empirical = proof_id in EMPIRICAL_PRODUCTION_PROOF_IDS
        artifact_ids = [evidence]
        evidence_ids = ["evidence"]
        if empirical:
            direct = fixture.direct_qualifications.get(proof_id)
            if direct is not None:
                artifact_ids.append(direct.artifact_id)
                evidence_ids.extend(
                    (direct.subject_id, direct.experiment_id, direct.semantic_evidence_id)
                )
            else:
                qualification_artifact, subject_id, experiment_id = _empirical_qualification(
                    store,
                    proof_id,
                )
                artifact_ids.append(qualification_artifact)
                evidence_ids.extend((subject_id, experiment_id))
        claims.append(
            AssuranceClaim(
                proof_id=proof_id,
                status=ProofStatus.SUPPORTED if empirical else ProofStatus.PROVEN,
                evidence_ids=tuple(evidence_ids),
                test_ids=("test",),
                artifact_ids=tuple(artifact_ids),
            )
        )
    case = AssuranceCase(
        release_scope=SCOPE,
        claims=tuple(claims),
    )
    backend = ProductionBackendQualification(
        artifact_store_backend_id=store.backend_id,
        release_registry_backend_id=registry.backend_id,
        artifact_store_qualification_artifact_id=store_q,
        release_registry_qualification_artifact_id=registry_q,
        durable_shared_artifact_store=True,
        durable_shared_release_registry=True,
        atomic_compare_and_swap=True,
        immutable_release_history=True,
        qualification_scope=SCOPE,
    )
    outcome = execute_production_cutover(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        bundle_id=fixture.bundle.bundle_id,
        world_id=fixture.bundle.world_id,
        runtime_digest="sha256:runtime-v2",
        created_at=CREATED_AT,
        valid_until=VALID_UNTIL,
        artifact_manifest_id=manifest,
        assurance_case=case,
        obligations=obligations,
        backend_qualification=backend,
        artifact_store=store,
        production_registry=registry,
    )
    return store, registry, outcome


def _resolve(store, registry, *, as_of: str = AS_OF):
    return resolve_production_answer_authority(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        as_of=as_of,
        artifact_store=store,
        production_registry=registry,
    )


def test_no_current_pointer_is_non_actionable_and_exposes_no_bundle(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    registry = FileSystemReleaseRegistry(tmp_path / "production")
    authority = _resolve(store, registry)
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert authority.ready_to_act is False
    assert authority.safe_to_act is False
    assert authority.production_result_bundle_id is None


def test_exact_current_proof_authorized_release_is_only_actionable_authority(tmp_path: Path) -> None:
    store, registry, outcome = _qualified_cutover(tmp_path)
    authority = _resolve(store, registry)
    assert authority.status is ProductionAuthorityStatus.CURRENT
    assert authority.ready_to_act is True
    assert authority.safe_to_act is True
    assert authority.release_id is not None
    assert str(authority.release_id) == outcome.release_record.release_id
    assert outcome.release_record.bundle_id is not None
    assert authority.production_result_bundle_id == BundleId(outcome.release_record.bundle_id)


def _make_current_record(
    *,
    store,
    registry,
    status: ReleaseStatus,
    ready: bool,
    safe: bool,
    authorization_artifact_id: str | None = None,
    expected_release_id: str | None = None,
    valid_until: str | None = VALID_UNTIL,
) -> ReleaseRecord:
    manifest = _artifact(store, f"manifest-{status.value}-{authorization_artifact_id}")
    record = registry.append(
        ReleaseRecord(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            bundle_id="forged-bundle",
            world_id="forged-world",
            runtime_digest="sha256:forged-runtime",
            created_at=CREATED_AT,
            valid_until=valid_until,
            status=status,
            ready_to_act=ready,
            safe_to_act=safe,
            artifact_manifest_id=manifest,
            publication_authorization_artifact_id=authorization_artifact_id,
        )
    )
    assert record.release_id is not None
    registry.compare_and_swap_current(
        ReleaseKey(SEASON, ENTRY, GAMEWEEK),
        expected_release_id=expected_release_id,
        new_release_id=record.release_id,
    )
    return record


def test_forged_published_ready_record_without_authorization_is_rejected(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    registry = FileSystemReleaseRegistry(tmp_path / "production")
    _make_current_record(
        store=store,
        registry=registry,
        status=ReleaseStatus.PUBLISHED,
        ready=True,
        safe=True,
    )
    authority = _resolve(store, registry)
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert "lacks proof-derived authorization" in authority.blockers[0]
    assert authority.production_result_bundle_id is None


def test_v1_and_certified_records_cannot_become_v2_answer_authority(tmp_path: Path) -> None:
    for index, status in enumerate((ReleaseStatus.V1_ACTIONABLE, ReleaseStatus.CERTIFIED), start=1):
        root = tmp_path / str(index)
        store = FileSystemArtifactStore(root / "artifacts")
        registry = FileSystemReleaseRegistry(root / "production")
        _make_current_record(
            store=store,
            registry=registry,
            status=status,
            ready=status is ReleaseStatus.V1_ACTIONABLE,
            safe=status is ReleaseStatus.V1_ACTIONABLE,
        )
        authority = _resolve(store, registry)
        assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
        assert authority.production_result_bundle_id is None
        assert "not V2 PUBLISHED" in authority.blockers[0]


def test_corrupt_publication_authorization_withholds_current_answer(tmp_path: Path) -> None:
    store, registry, outcome = _qualified_cutover(tmp_path)
    artifact_id = outcome.release_record.publication_authorization_artifact_id
    assert artifact_id is not None
    digest = artifact_id.split(":", 1)[1]
    path = tmp_path / "artifacts" / "objects" / "sha256" / digest[:2] / digest
    path.write_bytes(b"corrupt")
    authority = _resolve(store, registry)
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert authority.production_result_bundle_id is None
    assert "publication authorization is invalid" in authority.blockers[0]


def test_corrupt_production_bundle_withholds_current_answer(tmp_path: Path) -> None:
    store, registry, outcome = _qualified_cutover(tmp_path)
    bundle_id = outcome.release_record.bundle_id
    assert bundle_id is not None
    digest = bundle_id.split(":", 1)[1]
    path = tmp_path / "artifacts" / "objects" / "sha256" / digest[:2] / digest
    path.write_bytes(b"corrupt")

    authority = _resolve(store, registry)
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert authority.production_result_bundle_id is None
    assert "publication authorization is invalid" in authority.blockers[0]
    assert "production planning bundle" in authority.blockers[0]


def test_expired_current_release_is_non_actionable_even_when_pointer_is_current(tmp_path: Path) -> None:
    store, registry, _ = _qualified_cutover(tmp_path)
    authority = _resolve(store, registry, as_of=VALID_UNTIL)
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert authority.production_result_bundle_id is None
    assert "has expired" in authority.blockers[0]


def test_current_release_cannot_be_used_before_declared_creation_time(tmp_path: Path) -> None:
    store, registry, _ = _qualified_cutover(tmp_path)
    authority = _resolve(store, registry, as_of="2026-08-25T05:59:59Z")
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert authority.production_result_bundle_id is None
    assert "not yet valid" in authority.blockers[0]


def test_publication_authorization_validity_must_match_release_record(tmp_path: Path) -> None:
    store, registry, outcome = _qualified_cutover(tmp_path)
    current_id = outcome.release_record.release_id
    assert current_id is not None
    authorization_id = outcome.release_record.publication_authorization_artifact_id
    assert authorization_id is not None

    forged = registry.append(
        ReleaseRecord(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            bundle_id=outcome.release_record.bundle_id,
            world_id=outcome.release_record.world_id,
            runtime_digest=outcome.release_record.runtime_digest,
            created_at=outcome.release_record.created_at,
            valid_until="2026-08-30T10:00:00Z",
            status=ReleaseStatus.PUBLISHED,
            ready_to_act=True,
            safe_to_act=True,
            artifact_manifest_id=outcome.release_record.artifact_manifest_id,
            publication_authorization_artifact_id=authorization_id,
        )
    )
    assert forged.release_id is not None
    registry.compare_and_swap_current(
        ReleaseKey(SEASON, ENTRY, GAMEWEEK),
        expected_release_id=current_id,
        new_release_id=forged.release_id,
    )
    authority = _resolve(store, registry)
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert authority.production_result_bundle_id is None
    assert "validity does not match" in authority.blockers[0]


def test_authorization_cannot_be_replayed_through_different_backend_identities(tmp_path: Path) -> None:
    store, registry, _ = _qualified_cutover(tmp_path)
    alternate_store = _DurableArtifactStore(tmp_path / "artifacts")
    alternate_registry = _DurableReleaseRegistry(tmp_path / "production")
    alternate_store.backend_id = "test.production.other-artifact-store.v1"
    alternate_registry.backend_id = "test.production.other-release-registry.v1"

    authority = _resolve(alternate_store, alternate_registry)
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert authority.production_result_bundle_id is None
    assert "backend differs from publication authorization" in authority.blockers[0]


class _DriftingCurrentReader:
    backend_id = _DurableReleaseRegistry.backend_id

    def __init__(self, delegate: _DurableReleaseRegistry):
        self.delegate = delegate
        self.calls = 0

    def current_release_id(self, key: ReleaseKey) -> str | None:
        self.calls += 1
        value = self.delegate.current_release_id(key)
        return value if self.calls == 1 else "concurrent-new-release"

    def read_release(self, release_id: str):
        return self.delegate.read_release(release_id)


def test_answer_authority_withholds_if_current_pointer_changes_during_verification(
    tmp_path: Path,
) -> None:
    store, registry, _ = _qualified_cutover(tmp_path)
    authority = _resolve(store, _DriftingCurrentReader(registry))
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert authority.production_result_bundle_id is None
    assert "pointer changed during authority verification" in authority.blockers[0]
