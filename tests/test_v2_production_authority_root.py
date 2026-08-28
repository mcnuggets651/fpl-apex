from __future__ import annotations

import json
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.authority_root_backend_qualification import (
    load_authority_root_registry_qualification,
    qualify_authority_root_registry,
)
from apex_fpl.control.authority_root_registry import (
    AuthorityRootCompareAndSwapConflict,
    FileSystemAuthorityRootRegistry,
)
from apex_fpl.control.production_authority_root import (
    load_production_authority_root,
    store_production_authority_root,
)
from apex_fpl.core.artifact_manifest import (
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactManifestRole,
)
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.production_authority_root import ProductionAuthorityRoot


SEASON = "2026-27"


def _sha(label: str) -> str:
    return canonical_sha256(
        {
            "schema_name": "authority-root-test-id",
            "schema_version": 1,
            "label": label,
        }
    )


def _root(
    *,
    generation: int = 1,
    parent: str | None = None,
    suffix: str = "one",
    valid_from: str = "2026-08-27T12:00:00+00:00",
    valid_until: str = "2026-09-03T12:00:00+00:00",
) -> ProductionAuthorityRoot:
    return ProductionAuthorityRoot(
        season=SEASON,
        generation=generation,
        parent_root_artifact_id=parent,
        champion_generation_artifact_id=_sha(f"champion-{suffix}"),
        ruleset_artifact_id=_sha(f"ruleset-artifact-{suffix}"),
        ruleset_id=_sha(f"ruleset-{suffix}"),
        learning_policy_registry_artifact_id=_sha(f"learning-registry-{suffix}"),
        learning_policy_id=_sha(f"learning-policy-{suffix}"),
        outcome_truth_registry_artifact_id=_sha(f"truth-registry-artifact-{suffix}"),
        outcome_truth_registry_id=_sha(f"truth-registry-{suffix}"),
        build_manifest_artifact_id=_sha(f"build-manifest-artifact-{suffix}"),
        build_manifest_id=_sha(f"build-manifest-{suffix}"),
        change_control_artifact_id=_sha(f"change-control-{suffix}"),
        authorized_by="authority-reviewer",
        authorized_at="2026-08-27T11:00:00+00:00",
        valid_from=valid_from,
        valid_until=valid_until,
        reason=f"test authority root {suffix}",
    )


def test_production_authority_root_is_self_addressed_and_time_bounded(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    root = _root()
    artifact_id = store_production_authority_root(root, store=store)

    assert artifact_id == root.root_id
    assert load_production_authority_root(artifact_id, store=store) == root
    root.require_valid_at("2026-08-27T12:00:00+00:00")

    with pytest.raises(ValueError, match="not yet valid"):
        root.require_valid_at("2026-08-27T11:59:59+00:00")
    with pytest.raises(ValueError, match="has expired"):
        root.require_valid_at("2026-09-03T12:00:00+00:00")


def test_production_authority_root_requires_contiguous_parent_shape() -> None:
    first = _root()

    with pytest.raises(ValueError, match="later authority root requires parent"):
        _root(generation=2, suffix="missing-parent")
    with pytest.raises(ValueError, match="first authority root cannot have parent"):
        _root(generation=1, parent=first.root_id, suffix="unexpected-parent")


def test_filesystem_authority_root_registry_rejects_stale_writer(tmp_path: Path) -> None:
    registry = FileSystemAuthorityRootRegistry(tmp_path / "roots")
    first = _root()
    second = _root(generation=2, parent=first.root_id, suffix="two")
    stale = _root(generation=2, parent=first.root_id, suffix="stale")
    for root in (first, second, stale):
        registry.append(root)

    registry.compare_and_swap_current(SEASON, expected_root_id=None, new_root_id=first.root_id)
    registry.compare_and_swap_current(
        SEASON,
        expected_root_id=first.root_id,
        new_root_id=second.root_id,
    )

    with pytest.raises(AuthorityRootCompareAndSwapConflict, match="stale authority-root writer"):
        registry.compare_and_swap_current(
            SEASON,
            expected_root_id=first.root_id,
            new_root_id=stale.root_id,
        )

    assert registry.current_root_id(SEASON) == second.root_id
    assert registry.read_root(first.root_id) == first


def test_authority_root_registry_requires_parent_to_equal_cas_expectation(
    tmp_path: Path,
) -> None:
    registry = FileSystemAuthorityRootRegistry(tmp_path / "roots")
    first = _root()
    wrong_parent = _root(generation=2, parent=_sha("different-parent"), suffix="wrong-parent")
    registry.append(first)
    registry.append(wrong_parent)
    registry.compare_and_swap_current(SEASON, expected_root_id=None, new_root_id=first.root_id)

    with pytest.raises(ValueError, match="parent must equal CAS expected"):
        registry.compare_and_swap_current(
            SEASON,
            expected_root_id=first.root_id,
            new_root_id=wrong_parent.root_id,
        )


def test_filesystem_root_registry_mechanics_never_become_production_qualification(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    registry = FileSystemAuthorityRootRegistry(tmp_path / "roots")
    stored = qualify_authority_root_registry(
        registry,
        store=store,
        qualification_scope="2026-27:production",
        probe_nonce="reference-mechanics",
    )

    replayed = load_authority_root_registry_qualification(
        stored.artifact_id,
        store=store,
        expected_backend_id=registry.backend_id,
        expected_scope="2026-27:production",
    )
    assert replayed.qualification == stored.qualification
    assert stored.qualification.durable_shared_registry is True
    assert stored.qualification.immutable_root_history is True
    assert stored.qualification.atomic_compare_and_swap is True
    assert stored.qualification.stale_writer_rejected is True
    assert stored.qualification.qualified is False


def test_authority_root_registry_qualification_rejects_tampered_claim(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    registry = FileSystemAuthorityRootRegistry(tmp_path / "roots")
    stored = qualify_authority_root_registry(
        registry,
        store=store,
        qualification_scope="2026-27:production",
        probe_nonce="tamper",
    )
    envelope = json.loads(store.read_bytes(stored.artifact_id).decode("utf-8"))
    envelope["payload"]["atomic_compare_and_swap"] = False
    forged = store.put_bytes(canonical_json_bytes(envelope)).artifact_id

    with pytest.raises(ValueError, match="semantic identity mismatch"):
        load_authority_root_registry_qualification(forged, store=store)


def test_artifact_manifest_requires_authority_root_registry_qualification() -> None:
    bundle_id = _sha("bundle")
    world_id = _sha("world")
    authority_root_id = _sha("authority-root")
    entries = []
    for role in ArtifactManifestRole:
        if role is ArtifactManifestRole.AUTHORITY_ROOT_REGISTRY_QUALIFICATION:
            continue
        artifact_id = _sha(f"manifest-{role.value}")
        if role is ArtifactManifestRole.PLANNING_BUNDLE:
            artifact_id = bundle_id
        elif role is ArtifactManifestRole.WORLD:
            artifact_id = world_id
        elif role is ArtifactManifestRole.AUTHORITY_ROOT:
            artifact_id = authority_root_id
        entries.append(ArtifactManifestEntry(role=role, artifact_id=artifact_id))

    with pytest.raises(
        ValueError,
        match="AUTHORITY_ROOT_REGISTRY_QUALIFICATION",
    ):
        ArtifactManifest(
            season=SEASON,
            entry=63984,
            gameweek=2,
            bundle_id=bundle_id,
            world_id=world_id,
            runtime_digest=_sha("runtime"),
            authority_root_artifact_id=authority_root_id,
            entries=tuple(sorted(entries, key=lambda item: item.role.value)),
        )


def test_artifact_manifest_accepts_typed_sha256_semantic_identity() -> None:
    artifact_id = _sha("reference-solver-authorization-artifact")
    semantic_id = f"reference-solver-authorization:{_sha('authorization-semantic')}"

    entry = ArtifactManifestEntry(
        role=ArtifactManifestRole.REFERENCE_SOLVER_AUTHORIZATION,
        artifact_id=artifact_id,
        semantic_id=semantic_id,
    )

    assert entry.artifact_id == artifact_id
    assert entry.semantic_id == semantic_id


def test_artifact_manifest_rejects_malformed_typed_semantic_identity() -> None:
    with pytest.raises(ValueError, match="typed sha256 semantic identity"):
        ArtifactManifestEntry(
            role=ArtifactManifestRole.REFERENCE_SOLVER_AUTHORIZATION,
            artifact_id=_sha("reference-solver-authorization-artifact"),
            semantic_id="reference solver authorization:sha256:not-a-digest",
        )


def test_filesystem_pointer_rejects_malformed_root_identity(tmp_path: Path) -> None:
    registry = FileSystemAuthorityRootRegistry(tmp_path / "roots")
    pointer = registry._pointer_path(SEASON)  # noqa: SLF001 - adversarial persistence test
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(
        json.dumps(
            {
                "schema_name": "apex-authority-root-pointer",
                "schema_version": 1,
                "season": SEASON,
                "root_id": "sha256:" + "not-hex".ljust(64, "x"),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="digest is invalid"):
        registry.current_root_id(SEASON)
