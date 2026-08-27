from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.production_authority import resolve_production_answer_authority
from apex_fpl.control.production_authority_root import store_production_authority_root
from apex_fpl.control.production_cutover import execute_production_cutover
from apex_fpl.control.release_registry import FileSystemReleaseRegistry
from apex_fpl.core.ids import BundleId
from apex_fpl.core.production import MANDATORY_PRODUCTION_PROOF_IDS
from apex_fpl.core.production_authority import ProductionAuthorityStatus
from apex_fpl.core.production_proof_contract import (
    EMPIRICAL_PRODUCTION_PROOF_IDS,
    PRODUCTION_PROOF_CLASSES,
)
from apex_fpl.core.proofs import (
    AssuranceCase,
    AssuranceClaim,
    ProofObligation,
    ProofStatus,
    ReleasePolicy,
)

from _legacy_v2_production_authority import (
    _DurableArtifactStore,
    _DurableReleaseRegistry,
    _artifact,
    _empirical_qualification,
)
from backend_qualification_helpers import synthetic_production_backend_qualification
from champion_authority_helpers import synthetic_production_champion_authority
from production_authority_root_helpers import (
    RootedProductionAuthorityMaterial,
    build_rooted_production_authority_material,
)
from production_planning_bundle_helpers import synthetic_production_planning_bundle
from reference_solver_planning_helpers import synthetic_planning_parity_material


SEASON = "2026-2027"
ENTRY = 63984
GAMEWEEK = 2
SCOPE = f"{SEASON}:{ENTRY}:{GAMEWEEK}:production"
CREATED_AT = "2026-08-25T06:00:00Z"
VALID_UNTIL = "2026-08-29T10:00:00Z"
AS_OF = "2026-08-25T07:00:00Z"
ROOT_VALID_UNTIL = "2026-09-05T10:00:00Z"
PARITY_PROOF_ID = "PO-REFERENCE-SOLVER-PARITY-001"


def _release_policy_material(*, store, fixture, parity):
    evidence = _artifact(store, "proof-evidence")
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
        if proof_id == PARITY_PROOF_ID:
            artifact_ids.extend(parity.artifact_ids)
            evidence_ids.extend(parity.evidence_ids)
        claims.append(
            AssuranceClaim(
                proof_id=proof_id,
                status=ProofStatus.SUPPORTED if empirical else ProofStatus.PROVEN,
                evidence_ids=tuple(evidence_ids),
                test_ids=("test",),
                artifact_ids=tuple(artifact_ids),
            )
        )
    return (
        AssuranceCase(release_scope=SCOPE, claims=tuple(claims)),
        obligations,
    )


def _rooted_material(
    tmp_path: Path,
    *,
    root_valid_until: str = ROOT_VALID_UNTIL,
):
    store = _DurableArtifactStore(tmp_path / "artifacts")
    release_registry = _DurableReleaseRegistry(tmp_path / "production")
    fixture = synthetic_production_planning_bundle(
        store=store,
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
    )
    parity = synthetic_planning_parity_material(store=store, fixture=fixture)
    champion = synthetic_production_champion_authority(
        store=store,
        fixture=fixture,
        reviewed_at=CREATED_AT,
    )
    case, obligations = _release_policy_material(
        store=store,
        fixture=fixture,
        parity=parity,
    )
    backend = synthetic_production_backend_qualification(
        store=store,
        registry=release_registry,
        qualification_scope=SCOPE,
    ).qualification
    rooted = build_rooted_production_authority_material(
        tmp_path=tmp_path,
        store=store,
        fixture=fixture,
        parity=parity,
        champion=champion,
        assurance_case=case,
        obligations=obligations,
        backend_qualification=backend,
        authorized_at=CREATED_AT,
        root_valid_until=root_valid_until,
    )
    return store, release_registry, fixture, champion, case, obligations, backend, rooted


def _qualified_cutover(tmp_path: Path):
    (
        store,
        release_registry,
        fixture,
        champion,
        case,
        obligations,
        backend,
        rooted,
    ) = _rooted_material(tmp_path)
    outcome = execute_production_cutover(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        bundle_id=fixture.bundle.bundle_id,
        world_id=fixture.bundle.world_id,
        runtime_digest=rooted.runtime_digest,
        created_at=CREATED_AT,
        valid_until=VALID_UNTIL,
        artifact_manifest_id=rooted.artifact_manifest_id,
        assurance_case=case,
        obligations=obligations,
        backend_qualification=backend,
        artifact_store=store,
        production_registry=release_registry,
        champion_generation_artifact_id=champion.generation.artifact_id,
        authority_root_registry=rooted.authority_root_registry,
    )
    return store, release_registry, rooted, outcome


def _resolve(
    store,
    registry,
    rooted: RootedProductionAuthorityMaterial | None,
    *,
    as_of: str = AS_OF,
):
    return resolve_production_answer_authority(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        as_of=as_of,
        artifact_store=store,
        production_registry=registry,
        authority_root_registry=(
            None if rooted is None else rooted.authority_root_registry
        ),
    )


def test_no_current_release_pointer_is_non_actionable(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    registry = FileSystemReleaseRegistry(tmp_path / "production")
    authority = _resolve(store, registry, None)
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert authority.ready_to_act is False
    assert authority.safe_to_act is False
    assert authority.production_result_bundle_id is None


def test_exact_rooted_published_release_is_only_actionable_authority(tmp_path: Path) -> None:
    store, registry, rooted, outcome = _qualified_cutover(tmp_path)
    authority = _resolve(store, registry, rooted)
    assert authority.status is ProductionAuthorityStatus.CURRENT
    assert authority.ready_to_act is True
    assert authority.safe_to_act is True
    assert authority.release_id is not None
    assert str(authority.release_id) == outcome.release_record.release_id
    assert authority.production_result_bundle_id == BundleId(
        str(outcome.release_record.bundle_id)
    )


def test_published_release_without_root_registry_is_withheld(tmp_path: Path) -> None:
    store, registry, _, _ = _qualified_cutover(tmp_path)
    authority = _resolve(store, registry, None)
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert authority.production_result_bundle_id is None
    assert "AuthorityRootRegistry is required" in authority.blockers[0]


def test_answer_is_withheld_after_current_root_pointer_moves(tmp_path: Path) -> None:
    store, registry, rooted, _ = _qualified_cutover(tmp_path)
    first = rooted.root
    second = replace(
        first,
        generation=2,
        parent_root_artifact_id=first.root_id,
        authorized_at="2026-08-25T06:30:00Z",
        valid_from="2026-08-25T06:30:00Z",
        reason="synthetic successor authority root",
    )
    store_production_authority_root(second, store=store)
    rooted.authority_root_registry.append(second)
    rooted.authority_root_registry.compare_and_swap_current(
        SEASON,
        expected_root_id=first.root_id,
        new_root_id=second.root_id,
    )

    authority = _resolve(store, registry, rooted)
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert authority.production_result_bundle_id is None
    assert "current pointer does not match release manifest" in authority.blockers[0]


def test_cutover_rejects_root_that_does_not_cover_release_horizon(tmp_path: Path) -> None:
    (
        store,
        release_registry,
        fixture,
        champion,
        case,
        obligations,
        backend,
        rooted,
    ) = _rooted_material(
        tmp_path,
        root_valid_until="2026-08-29T09:59:59Z",
    )
    with pytest.raises(ValueError, match="does not cover the full release validity horizon"):
        execute_production_cutover(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            bundle_id=fixture.bundle.bundle_id,
            world_id=fixture.bundle.world_id,
            runtime_digest=rooted.runtime_digest,
            created_at=CREATED_AT,
            valid_until=VALID_UNTIL,
            artifact_manifest_id=rooted.artifact_manifest_id,
            assurance_case=case,
            obligations=obligations,
            backend_qualification=backend,
            artifact_store=store,
            production_registry=release_registry,
            champion_generation_artifact_id=champion.generation.artifact_id,
            authority_root_registry=rooted.authority_root_registry,
        )


def test_corrupt_production_bundle_withholds_rooted_answer(tmp_path: Path) -> None:
    store, registry, rooted, outcome = _qualified_cutover(tmp_path)
    bundle_id = str(outcome.release_record.bundle_id)
    digest = bundle_id.split(":", 1)[1]
    path = store.root / "objects" / "sha256" / digest[:2] / digest
    path.write_bytes(b"corrupt")

    authority = _resolve(store, registry, rooted)
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert authority.production_result_bundle_id is None


def test_rooted_release_obeys_release_validity_window(tmp_path: Path) -> None:
    store, registry, rooted, _ = _qualified_cutover(tmp_path)
    before = _resolve(
        store,
        registry,
        rooted,
        as_of="2026-08-25T05:59:59Z",
    )
    expired = _resolve(store, registry, rooted, as_of=VALID_UNTIL)
    assert before.status is ProductionAuthorityStatus.UNAVAILABLE
    assert expired.status is ProductionAuthorityStatus.UNAVAILABLE
    assert before.production_result_bundle_id is None
    assert expired.production_result_bundle_id is None
