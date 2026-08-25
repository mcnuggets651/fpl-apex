from __future__ import annotations

from pathlib import Path

import pytest

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
from apex_fpl.control.production_cutover import (
    execute_production_cutover,
    load_production_cutover_report,
)
from apex_fpl.control.release_registry import (
    CompareAndSwapConflict,
    FileSystemReleaseRegistry,
    ReleaseKey,
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
from apex_fpl.core.production import (
    MANDATORY_PRODUCTION_PROOF_IDS,
    ProductionBackendQualification,
    ProductionCutoverStatus,
)
from apex_fpl.core.production_proof_contract import (
    EMPIRICAL_PRODUCTION_PROOF_IDS,
    PRODUCTION_EMPIRICAL_SUBJECT_KIND,
    PRODUCTION_PROOF_CLASSES,
)
from apex_fpl.core.proofs import (
    AssuranceCase,
    AssuranceClaim,
    ProofClass,
    ProofObligation,
    ProofStatus,
    ReleasePolicy,
)

from production_bundle_helpers import synthetic_production_bundle
from production_planning_bundle_helpers import (
    DirectQualificationMaterial,
    synthetic_production_planning_bundle,
)


SEASON = "2026-2027"
ENTRY = 63984
GAMEWEEK = 2
SCOPE = f"{SEASON}:{ENTRY}:{GAMEWEEK}:production"
CREATED_AT = "2026-08-25T06:00:00Z"
VALID_UNTIL = "2026-08-29T10:00:00Z"


class _DurableArtifactStore:
    """Test double for a separately qualified durable shared ArtifactStore adapter."""

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
    """Test double for a separately qualified durable shared ReleaseRegistry adapter."""

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


def _artifact(store, value: str) -> str:
    return store.put_bytes(value.encode("utf-8")).artifact_id


def _fixture(store):
    return synthetic_production_planning_bundle(
        store=store,
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
    )


def _obligations() -> tuple[ProofObligation, ...]:
    return tuple(
        ProofObligation(
            proof_id=proof_id,
            claim=f"synthetic pre-publication production proof for {proof_id}",
            proof_class=PRODUCTION_PROOF_CLASSES[proof_id],
            scope="production-test",
            required_evidence=("synthetic-evidence",),
            required_tests=("synthetic-test",),
            failure_consequence="withhold production",
            release_policy=ReleasePolicy.REQUIRED,
            owner="tests",
        )
        for proof_id in sorted(MANDATORY_PRODUCTION_PROOF_IDS)
    )


def _empirical_qualification(store, proof_id: str) -> tuple[str, str, str]:
    """Build synthetic mechanism evidence; never a real production qualification."""

    subject_id = f"synthetic-subject:{proof_id}"
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
    registry = ExperimentRegistry(
        season=SEASON,
        registrations=(
            ExperimentRegistration(
                experiment_id=definition.experiment_id,
                definition_artifact_id=definition_ref.artifact_id,
            ),
        ),
    )
    registry_ref = store_experiment_registry(registry, store=store)
    certificate = derive_empirical_qualification_certificate(
        definition_artifact_id=definition_ref.artifact_id,
        result_artifact_id=result_ref.artifact_id,
        registry_artifact_id=registry_ref.artifact_id,
        store=store,
    )
    certificate_ref = store_empirical_qualification_certificate(certificate, store=store)
    assert certificate.supported is True
    return certificate_ref.artifact_id, subject_id, definition.experiment_id


def _direct_claim_evidence(material: DirectQualificationMaterial):
    return (
        material.artifact_id,
        material.subject_id,
        material.experiment_id,
        material.semantic_evidence_id,
    )


def _case(
    store,
    claim_artifact: str,
    *,
    missing: str | None = None,
    inconclusive: str | None = None,
    scope: str = SCOPE,
) -> AssuranceCase:
    direct = _fixture(store).direct_qualifications
    claims = []
    for proof_id in sorted(MANDATORY_PRODUCTION_PROOF_IDS):
        if proof_id == missing:
            continue
        empirical = proof_id in EMPIRICAL_PRODUCTION_PROOF_IDS
        artifact_ids = [claim_artifact]
        evidence_ids = ["synthetic-evidence"]
        if empirical and proof_id != inconclusive:
            if proof_id in direct:
                qualification_artifact, subject_id, experiment_id, semantic_id = (
                    _direct_claim_evidence(direct[proof_id])
                )
                artifact_ids.append(qualification_artifact)
                evidence_ids.extend((subject_id, experiment_id, semantic_id))
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
                status=(
                    ProofStatus.INCONCLUSIVE
                    if proof_id == inconclusive
                    else ProofStatus.SUPPORTED
                    if empirical
                    else ProofStatus.PROVEN
                ),
                evidence_ids=tuple(evidence_ids),
                test_ids=("synthetic-test",),
                artifact_ids=tuple(artifact_ids),
            )
        )
    return AssuranceCase(release_scope=scope, claims=tuple(claims))


def _backend(store, registry, *, qualified: bool = True, scope: str = SCOPE):
    return ProductionBackendQualification(
        artifact_store_backend_id=store.backend_id,
        release_registry_backend_id=registry.backend_id,
        artifact_store_qualification_artifact_id=_artifact(store, "artifact-store-qualified"),
        release_registry_qualification_artifact_id=_artifact(store, "registry-qualified"),
        durable_shared_artifact_store=qualified,
        durable_shared_release_registry=qualified,
        atomic_compare_and_swap=qualified,
        immutable_release_history=qualified,
        qualification_scope=scope,
    )


def _execute(
    tmp_path: Path,
    *,
    case: AssuranceCase | None = None,
    obligations: tuple[ProofObligation, ...] | None = None,
    backend: ProductionBackendQualification | None = None,
    store=None,
    registry=None,
    valid_until: str | None = VALID_UNTIL,
):
    store = store or _DurableArtifactStore(tmp_path / "artifacts")
    registry = registry or _DurableReleaseRegistry(tmp_path / "production")
    fixture = _fixture(store)
    manifest = _artifact(store, "manifest")
    claim_artifact = _artifact(store, "claim")
    return store, registry, execute_production_cutover(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        bundle_id=fixture.bundle.bundle_id,
        world_id=fixture.bundle.world_id,
        runtime_digest="sha256:v2-runtime",
        created_at=CREATED_AT,
        valid_until=valid_until,
        artifact_manifest_id=manifest,
        assurance_case=case or _case(store, claim_artifact),
        obligations=obligations or _obligations(),
        backend_qualification=backend or _backend(store, registry),
        artifact_store=store,
        production_registry=registry,
    )


def test_production_cutover_publishes_only_after_complete_pass_and_exact_cas(tmp_path: Path) -> None:
    store, registry, outcome = _execute(tmp_path)
    key = ReleaseKey(SEASON, ENTRY, GAMEWEEK)

    assert outcome.report.status is ProductionCutoverStatus.PUBLISHED
    assert outcome.report.release_certificate_status == "PASS"
    assert outcome.report.release_certificate_blockers == ()
    assert outcome.report.cutover_blockers == ()
    assert outcome.report.ready_to_act is True
    assert outcome.report.safe_to_act is True
    assert outcome.release_record.status is ReleaseStatus.PUBLISHED
    assert outcome.release_record.ready_to_act is True
    assert outcome.release_record.safe_to_act is True
    assert outcome.release_record.valid_until == VALID_UNTIL
    assert registry.current_release_id(key) == outcome.release_record.release_id
    assert registry.read_release(outcome.release_record.release_id or "") == outcome.release_record
    replayed = load_production_cutover_report(
        outcome.report_artifact_id,
        artifact_store=store,
    )
    assert replayed.report_id == outcome.report.report_id


def test_legacy_v1_bundle_is_rejected_before_pointer_write(tmp_path: Path) -> None:
    store = _DurableArtifactStore(tmp_path / "artifacts")
    registry = _DurableReleaseRegistry(tmp_path / "production")
    legacy = synthetic_production_bundle(
        store=store,
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
    )
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")

    with pytest.raises(ValueError, match="schema-v2 planning bundle"):
        execute_production_cutover(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            bundle_id=legacy.bundle.bundle_id,
            world_id=legacy.bundle.world_id,
            runtime_digest="sha256:v2-runtime",
            created_at=CREATED_AT,
            valid_until=VALID_UNTIL,
            artifact_manifest_id=manifest,
            assurance_case=_case(store, claim),
            obligations=_obligations(),
            backend_qualification=_backend(store, registry),
            artifact_store=store,
            production_registry=registry,
        )
    assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None


def test_incomplete_constitutional_proof_surface_is_rejected_before_pointer_write(
    tmp_path: Path,
) -> None:
    obligations = _obligations()[1:]
    store = _DurableArtifactStore(tmp_path / "artifacts")
    registry = _DurableReleaseRegistry(tmp_path / "production")
    fixture = _fixture(store)
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    with pytest.raises(ValueError, match="proof surface is incomplete"):
        execute_production_cutover(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            bundle_id=fixture.bundle.bundle_id,
            world_id=fixture.bundle.world_id,
            runtime_digest="sha256:v2-runtime",
            created_at=CREATED_AT,
            valid_until=VALID_UNTIL,
            artifact_manifest_id=manifest,
            assurance_case=_case(store, claim),
            obligations=obligations,
            backend_qualification=_backend(store, registry),
            artifact_store=store,
            production_registry=registry,
        )
    assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None


def test_proof_class_laundering_is_rejected_before_pointer_write(tmp_path: Path) -> None:
    store = _DurableArtifactStore(tmp_path / "artifacts")
    registry = _DurableReleaseRegistry(tmp_path / "production")
    fixture = _fixture(store)
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    target = sorted(EMPIRICAL_PRODUCTION_PROOF_IDS)[0]
    obligations = tuple(
        ProofObligation(
            proof_id=item.proof_id,
            claim=item.claim,
            proof_class=(
                ProofClass.FORMAL_INVARIANT if item.proof_id == target else item.proof_class
            ),
            scope=item.scope,
            required_evidence=item.required_evidence,
            required_tests=item.required_tests,
            failure_consequence=item.failure_consequence,
            release_policy=item.release_policy,
            owner=item.owner,
        )
        for item in _obligations()
    )
    with pytest.raises(ValueError, match="proof class drifted"):
        execute_production_cutover(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            bundle_id=fixture.bundle.bundle_id,
            world_id=fixture.bundle.world_id,
            runtime_digest="sha256:v2-runtime",
            created_at=CREATED_AT,
            valid_until=VALID_UNTIL,
            artifact_manifest_id=manifest,
            assurance_case=_case(store, claim),
            obligations=obligations,
            backend_qualification=_backend(store, registry),
            artifact_store=store,
            production_registry=registry,
        )
    assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None


def test_random_artifact_cannot_satisfy_empirical_production_proof(tmp_path: Path) -> None:
    store = _DurableArtifactStore(tmp_path / "artifacts")
    registry = _DurableReleaseRegistry(tmp_path / "production")
    fixture = _fixture(store)
    manifest = _artifact(store, "manifest")
    random_artifact = _artifact(store, "this-is-not-a-qualification-certificate")
    target = sorted(EMPIRICAL_PRODUCTION_PROOF_IDS)[0]
    good_case = _case(store, _artifact(store, "claim"))
    claims = []
    for claim in good_case.claims:
        if claim.proof_id == target:
            claims.append(
                AssuranceClaim(
                    proof_id=target,
                    status=ProofStatus.SUPPORTED,
                    evidence_ids=("synthetic-evidence", "fake-subject", "fake-experiment"),
                    test_ids=claim.test_ids,
                    artifact_ids=(random_artifact,),
                )
            )
        else:
            claims.append(claim)
    with pytest.raises(ValueError, match="lacks matching typed qualification evidence"):
        execute_production_cutover(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            bundle_id=fixture.bundle.bundle_id,
            world_id=fixture.bundle.world_id,
            runtime_digest="sha256:v2-runtime",
            created_at=CREATED_AT,
            valid_until=VALID_UNTIL,
            artifact_manifest_id=manifest,
            assurance_case=AssuranceCase(release_scope=SCOPE, claims=tuple(claims)),
            obligations=_obligations(),
            backend_qualification=_backend(store, registry),
            artifact_store=store,
            production_registry=registry,
        )
    assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None


def test_direct_policy_qualification_cannot_authorize_different_bundle_policy(tmp_path: Path) -> None:
    store = _DurableArtifactStore(tmp_path / "artifacts")
    registry = _DurableReleaseRegistry(tmp_path / "production")
    fixture = _fixture(store)
    manifest = _artifact(store, "manifest")
    good_case = _case(store, _artifact(store, "claim"))
    policy_claim = next(
        claim
        for claim in good_case.claims
        if claim.proof_id == "PO-DECISION-POLICY-QUALIFICATION-001"
    )
    unrelated_artifact, unrelated_subject, unrelated_experiment = _empirical_qualification(
        store,
        "PO-DECISION-POLICY-QUALIFICATION-001",
    )
    claims = tuple(
        AssuranceClaim(
            proof_id=claim.proof_id,
            status=claim.status,
            evidence_ids=(
                "synthetic-evidence",
                unrelated_subject,
                unrelated_experiment,
                policy_claim.evidence_ids[-1],
            ),
            test_ids=claim.test_ids,
            artifact_ids=(claim.artifact_ids[0], unrelated_artifact),
        )
        if claim.proof_id == "PO-DECISION-POLICY-QUALIFICATION-001"
        else claim
        for claim in good_case.claims
    )
    with pytest.raises(ValueError, match="PO-DECISION-POLICY-QUALIFICATION-001"):
        execute_production_cutover(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            bundle_id=fixture.bundle.bundle_id,
            world_id=fixture.bundle.world_id,
            runtime_digest="sha256:v2-runtime",
            created_at=CREATED_AT,
            valid_until=VALID_UNTIL,
            artifact_manifest_id=manifest,
            assurance_case=AssuranceCase(release_scope=SCOPE, claims=claims),
            obligations=_obligations(),
            backend_qualification=_backend(store, registry),
            artifact_store=store,
            production_registry=registry,
        )
    assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None


def test_missing_required_proof_withholds_and_never_moves_production_pointer(tmp_path: Path) -> None:
    store = _DurableArtifactStore(tmp_path / "artifacts")
    registry = _DurableReleaseRegistry(tmp_path / "production")
    fixture = _fixture(store)
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    missing = sorted(MANDATORY_PRODUCTION_PROOF_IDS)[0]
    outcome = execute_production_cutover(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        bundle_id=fixture.bundle.bundle_id,
        world_id=fixture.bundle.world_id,
        runtime_digest="sha256:v2-runtime",
        created_at=CREATED_AT,
        valid_until=VALID_UNTIL,
        artifact_manifest_id=manifest,
        assurance_case=_case(store, claim, missing=missing),
        obligations=_obligations(),
        backend_qualification=_backend(store, registry),
        artifact_store=store,
        production_registry=registry,
    )

    assert outcome.report.status is ProductionCutoverStatus.WITHHELD
    assert outcome.report.release_certificate_status == "FAIL"
    assert any(missing in blocker for blocker in outcome.report.release_certificate_blockers)
    assert outcome.report.ready_to_act is False
    assert outcome.report.safe_to_act is False
    assert outcome.release_record.status is ReleaseStatus.WITHHELD
    assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None


def test_unqualified_backend_withholds_even_when_release_certificate_passes(tmp_path: Path) -> None:
    store = _DurableArtifactStore(tmp_path / "artifacts")
    registry = _DurableReleaseRegistry(tmp_path / "production")
    fixture = _fixture(store)
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    outcome = execute_production_cutover(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        bundle_id=fixture.bundle.bundle_id,
        world_id=fixture.bundle.world_id,
        runtime_digest="sha256:v2-runtime",
        created_at=CREATED_AT,
        valid_until=VALID_UNTIL,
        artifact_manifest_id=manifest,
        assurance_case=_case(store, claim),
        obligations=_obligations(),
        backend_qualification=_backend(store, registry, qualified=False),
        artifact_store=store,
        production_registry=registry,
    )

    assert outcome.report.release_certificate_status == "PASS"
    assert outcome.report.status is ProductionCutoverStatus.WITHHELD
    assert outcome.report.cutover_blockers == (
        "production ArtifactStore/ReleaseRegistry control plane is not qualified",
    )
    assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None


def test_reference_filesystem_backends_cannot_be_qualified_by_green_booleans(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    registry = FileSystemReleaseRegistry(tmp_path / "production")
    fixture = _fixture(store)
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    backend = _backend(store, registry, qualified=True)
    assert backend.qualified is False

    outcome = execute_production_cutover(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        bundle_id=fixture.bundle.bundle_id,
        world_id=fixture.bundle.world_id,
        runtime_digest="sha256:v2-runtime",
        created_at=CREATED_AT,
        valid_until=VALID_UNTIL,
        artifact_manifest_id=manifest,
        assurance_case=_case(store, claim),
        obligations=_obligations(),
        backend_qualification=backend,
        artifact_store=store,
        production_registry=registry,
    )
    assert outcome.report.status is ProductionCutoverStatus.WITHHELD
    assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None


def test_backend_qualification_must_match_actual_adapter_identities(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    registry = FileSystemReleaseRegistry(tmp_path / "production")
    fixture = _fixture(store)
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    backend = ProductionBackendQualification(
        artifact_store_backend_id="some.other.artifact-store",
        release_registry_backend_id="some.other.release-registry",
        artifact_store_qualification_artifact_id=_artifact(store, "store-q"),
        release_registry_qualification_artifact_id=_artifact(store, "registry-q"),
        durable_shared_artifact_store=True,
        durable_shared_release_registry=True,
        atomic_compare_and_swap=True,
        immutable_release_history=True,
        qualification_scope=SCOPE,
    )
    with pytest.raises(ValueError, match="backend identity does not match qualification"):
        execute_production_cutover(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            bundle_id=fixture.bundle.bundle_id,
            world_id=fixture.bundle.world_id,
            runtime_digest="sha256:v2-runtime",
            created_at=CREATED_AT,
            valid_until=VALID_UNTIL,
            artifact_manifest_id=manifest,
            assurance_case=_case(store, claim),
            obligations=_obligations(),
            backend_qualification=backend,
            artifact_store=store,
            production_registry=registry,
        )
    assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None


def test_missing_or_invalid_validity_horizon_withholds(tmp_path: Path) -> None:
    for index, valid_until in enumerate((None, CREATED_AT), start=1):
        root = tmp_path / str(index)
        _, registry, outcome = _execute(root, valid_until=valid_until)
        assert outcome.report.status is ProductionCutoverStatus.WITHHELD
        assert outcome.report.ready_to_act is False
        assert outcome.release_record.status is ReleaseStatus.WITHHELD
        assert outcome.report.cutover_blockers
        assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None


class _StaleRegistry(_DurableReleaseRegistry):
    def compare_and_swap_current(self, key, *, expected_release_id, new_release_id):
        raise CompareAndSwapConflict("synthetic stale production writer")


def test_stale_writer_fails_closed_and_cannot_become_current(tmp_path: Path) -> None:
    store = _DurableArtifactStore(tmp_path / "artifacts")
    registry = _StaleRegistry(tmp_path / "production")
    fixture = _fixture(store)
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    with pytest.raises(CompareAndSwapConflict, match="stale production"):
        execute_production_cutover(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            bundle_id=fixture.bundle.bundle_id,
            world_id=fixture.bundle.world_id,
            runtime_digest="sha256:v2-runtime",
            created_at=CREATED_AT,
            valid_until=VALID_UNTIL,
            artifact_manifest_id=manifest,
            assurance_case=_case(store, claim),
            obligations=_obligations(),
            backend_qualification=_backend(store, registry),
            artifact_store=store,
            production_registry=registry,
        )
    assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None


def test_production_replay_rejects_lost_or_corrupt_source_evidence(tmp_path: Path) -> None:
    store, _, outcome = _execute(tmp_path)
    source_id = outcome.report.backend_qualification_artifact_ids[0]
    digest = source_id.split(":", 1)[1]
    object_path = (
        tmp_path / "artifacts" / "objects" / "sha256" / digest[:2] / digest
    )
    object_path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="production replay source"):
        load_production_cutover_report(
            outcome.report_artifact_id,
            artifact_store=store,
        )


def test_release_registry_read_rejects_tampered_release_bytes(tmp_path: Path) -> None:
    _, registry, outcome = _execute(tmp_path)
    release_id = outcome.release_record.release_id
    assert release_id is not None
    path = tmp_path / "production" / "releases" / f"{release_id}.json"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="declared identity mismatch"):
        registry.read_release(release_id)
