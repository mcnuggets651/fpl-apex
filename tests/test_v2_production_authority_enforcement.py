from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.authority_root_registry import FileSystemAuthorityRootRegistry
from apex_fpl.control.production_authority import resolve_production_answer_authority
from apex_fpl.control.production_authority_verification import (
    VerifiedProductionAuthorityClosure,
    require_authority_root_unchanged,
)
from apex_fpl.control.production_cutover import execute_production_cutover
from apex_fpl.control.release_registry import FileSystemReleaseRegistry, ReleaseKey, ReleaseRecord, ReleaseStatus
from apex_fpl.core.production_authority import ProductionAuthorityStatus


SEASON = "2026-2027"
ENTRY = 63984
GAMEWEEK = 2


def test_public_cutover_requires_authority_root_before_publication() -> None:
    with pytest.raises(ValueError, match="AuthorityRootRegistry is required"):
        execute_production_cutover(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            bundle_id=None,
            world_id=None,
            runtime_digest="sha256:" + "1" * 64,
            created_at="2026-08-27T12:00:00+00:00",
            valid_until="2026-08-28T12:00:00+00:00",
            artifact_manifest_id="sha256:" + "2" * 64,
            assurance_case=None,  # type: ignore[arg-type]
            obligations=(),
            backend_qualification=None,  # type: ignore[arg-type]
            artifact_store=None,  # type: ignore[arg-type]
            production_registry=None,  # type: ignore[arg-type]
            champion_generation_artifact_id=None,
            authority_root_registry=None,
        )


def test_actionable_release_is_unavailable_without_authority_root_registry(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    registry = FileSystemReleaseRegistry(tmp_path / "releases")
    manifest_id = store.put_bytes(b"legacy-manifest").artifact_id
    record = registry.append(
        ReleaseRecord(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            bundle_id="sha256:" + "3" * 64,
            world_id="sha256:" + "4" * 64,
            runtime_digest="sha256:" + "5" * 64,
            created_at="2026-08-27T12:00:00+00:00",
            valid_until="2026-08-28T12:00:00+00:00",
            status=ReleaseStatus.PUBLISHED,
            ready_to_act=True,
            safe_to_act=True,
            artifact_manifest_id=manifest_id,
            publication_authorization_artifact_id="sha256:" + "6" * 64,
        )
    )
    assert record.release_id is not None
    registry.compare_and_swap_current(
        ReleaseKey(SEASON, ENTRY, GAMEWEEK),
        expected_release_id=None,
        new_release_id=record.release_id,
    )

    authority = resolve_production_answer_authority(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        as_of="2026-08-27T13:00:00+00:00",
        artifact_store=store,
        production_registry=registry,
        authority_root_registry=None,
    )
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert authority.ready_to_act is False
    assert "AuthorityRootRegistry is required" in authority.blockers[0]


def test_root_pointer_drift_is_rejected(tmp_path: Path) -> None:
    registry = FileSystemAuthorityRootRegistry(tmp_path / "roots")
    first = "sha256:" + "7" * 64
    closure = VerifiedProductionAuthorityClosure(
        manifest=None,  # type: ignore[arg-type]
        authority=None,  # type: ignore[arg-type]
        registry_qualification=None,  # type: ignore[arg-type]
        current_root_id=first,
    )

    class _DriftedRegistry:
        backend_id = registry.backend_id

        @staticmethod
        def current_root_id(season: str) -> str | None:
            assert season == SEASON
            return "sha256:" + "8" * 64

        def read_root(self, root_id: str):  # pragma: no cover - protocol only
            raise AssertionError(root_id)

        def append(self, root):  # pragma: no cover - protocol only
            raise AssertionError(root)

        def compare_and_swap_current(self, season, *, expected_root_id, new_root_id):  # pragma: no cover
            raise AssertionError((season, expected_root_id, new_root_id))

    with pytest.raises(ValueError, match="pointer changed during resolution"):
        require_authority_root_unchanged(
            closure,
            season=SEASON,
            authority_root_registry=_DriftedRegistry(),
        )


def test_private_cutover_engine_has_no_unapproved_source_importers() -> None:
    control = Path(__file__).resolve().parents[1] / "src" / "apex_fpl" / "control"
    allowed = {"production_cutover.py", "production_authority_verification.py"}
    offenders = []
    for path in sorted(control.glob("*.py")):
        if path.name == "_production_cutover_legacy.py":
            continue
        if "_production_cutover_legacy" in path.read_text(encoding="utf-8") and path.name not in allowed:
            offenders.append(path.name)
    assert offenders == []
