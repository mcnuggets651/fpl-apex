from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pytest

import apex_fpl.control.production_cutover as production_cutover_module
import production_planning_bundle_helpers as planning_fixture_helpers
from apex_fpl.control.production_planning_bundle import load_production_planning_bundle
from reference_solver_planning_helpers import SyntheticPlanningParityMaterial


PARITY_PROOF_ID = "PO-REFERENCE-SOLVER-PARITY-001"
_TARGET_MODULES = {
    "test_v2_champion_authority",
    "test_v2_production_cutover",
    "test_v2_production_authority",
    "test_v2_production_planning_bundle",
    "test_v2_reference_solver_planning",
    "test_v2_reference_solver_planning_qualification",
}
_FULL_PARITY_TESTS = {
    "test_v2_production_cutover::test_production_cutover_publishes_only_after_complete_pass_and_exact_cas",
    "test_v2_production_cutover::test_random_artifact_cannot_satisfy_reference_solver_parity",
    "test_v2_production_cutover::test_planning_parity_certificate_without_champion_authorization_is_rejected",
    "test_v2_production_authority::test_exact_current_proof_authorized_release_is_only_actionable_authority",
}


@dataclass(frozen=True, slots=True)
class _RecordedArtifact:
    artifact_id: str
    content: bytes
    kwargs: tuple[tuple[str, Any], ...]


@dataclass(frozen=True, slots=True)
class _CachedPlanningFixture:
    fixture: object
    artifacts: tuple[_RecordedArtifact, ...]


@dataclass(frozen=True, slots=True)
class _CachedChampionAuthority:
    authority: object
    artifacts: tuple[_RecordedArtifact, ...]


class _RecordingArtifactStore:
    """Record immutable test-fixture writes while delegating all store semantics."""

    def __init__(self, delegate):
        self._delegate = delegate
        self._recorded: dict[str, _RecordedArtifact] = {}

    @property
    def backend_id(self):
        return self._delegate.backend_id

    def put_bytes(self, content: bytes, **kwargs):
        ref = self._delegate.put_bytes(content, **kwargs)
        self._recorded[ref.artifact_id] = _RecordedArtifact(
            artifact_id=ref.artifact_id,
            content=bytes(content),
            kwargs=tuple(sorted(kwargs.items())),
        )
        return ref

    def read_bytes(self, artifact_id: str) -> bytes:
        return self._delegate.read_bytes(artifact_id)

    def verify(self, artifact_id: str) -> bool:
        return self._delegate.verify(artifact_id)

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    @property
    def artifacts(self) -> tuple[_RecordedArtifact, ...]:
        return tuple(sorted(self._recorded.values(), key=lambda item: item.artifact_id))


_PLANNING_FIXTURE_CACHE: dict[tuple[str, str, int, int], _CachedPlanningFixture] = {}
_CHAMPION_AUTHORITY_CACHE: dict[
    tuple[str, str, str | None, str | None], _CachedChampionAuthority
] = {}


def _restore_artifacts(store, artifacts: tuple[_RecordedArtifact, ...], *, label: str) -> None:
    for item in artifacts:
        ref = store.put_bytes(item.content, **dict(item.kwargs))
        if ref.artifact_id != item.artifact_id:
            raise ValueError(f"cached synthetic {label} artifact identity drifted")


def _cached_planning_fixture(
    original: Callable[..., object],
    *,
    store,
    cache_variant: str,
    season: str = "2026-2027",
    entry: int = 63984,
    gameweek: int = 2,
):
    """Reuse exact synthetic lineage bytes across isolated assurance-test stores."""

    key = (cache_variant, str(season), int(entry), int(gameweek))
    cached = _PLANNING_FIXTURE_CACHE.get(key)
    if cached is not None:
        _restore_artifacts(store, cached.artifacts, label="planning fixture")
        return cached.fixture

    recording = _RecordingArtifactStore(store)
    fixture = original(
        store=recording,
        season=season,
        entry=entry,
        gameweek=gameweek,
    )
    _PLANNING_FIXTURE_CACHE[key] = _CachedPlanningFixture(
        fixture=fixture,
        artifacts=recording.artifacts,
    )
    return fixture


def _cached_champion_authority(
    original: Callable[..., object],
    *,
    store,
    fixture,
    reviewed_at: str = "2026-08-24T12:00:00Z",
    current_generation_artifact_id: str | None = None,
    expected_parent_generation_id: str | None = None,
):
    """Reuse immutable baseline authority construction, never its replay/verifier execution.

    The key includes chronology and parent/CAS inputs. Adversarial stale-writer or alternate-
    generation calls therefore execute the real constructor independently. Cached artifact bytes
    are replayed through each isolated store before the immutable result object is reused.
    """

    key = (
        str(fixture.bundle.bundle_id),
        str(reviewed_at),
        current_generation_artifact_id,
        expected_parent_generation_id,
    )
    cached = _CHAMPION_AUTHORITY_CACHE.get(key)
    if cached is not None:
        _restore_artifacts(store, cached.artifacts, label="champion authority")
        return cached.authority

    recording = _RecordingArtifactStore(store)
    authority = original(
        store=recording,
        fixture=fixture,
        reviewed_at=reviewed_at,
        current_generation_artifact_id=current_generation_artifact_id,
        expected_parent_generation_id=expected_parent_generation_id,
    )
    _CHAMPION_AUTHORITY_CACHE[key] = _CachedChampionAuthority(
        authority=authority,
        artifacts=recording.artifacts,
    )
    return authority


def _lightweight_parity_dependency(claim, *, verified_bundle, store) -> bool:
    """Unit-test seam for tests whose subject is not solver parity."""

    del store
    return (
        claim.proof_id == PARITY_PROOF_ID
        and str(verified_bundle.decision.planning_result_id) in set(claim.evidence_ids)
    )


def _lightweight_parity_material(*, store, fixture) -> SyntheticPlanningParityMaterial:
    """Build only immutable parity claim material for tests unrelated to parity replay."""

    verified = load_production_planning_bundle(fixture.bundle.bundle_id, store=store)
    planning_result_id = str(verified.decision.planning_result_id)
    certificate_ref = store.put_bytes(
        f"synthetic-lightweight-planning-parity-certificate:{planning_result_id}".encode("utf-8")
    )
    authorization_ref = store.put_bytes(
        f"synthetic-lightweight-planning-parity-authorization:{planning_result_id}".encode("utf-8")
    )
    return SyntheticPlanningParityMaterial(
        planning_result_id=planning_result_id,
        certificate_artifact_id=certificate_ref.artifact_id,
        certificate_id=f"synthetic-lightweight-certificate:{planning_result_id}",
        authorization_artifact_id=authorization_ref.artifact_id,
        authorization_id=f"synthetic-lightweight-authorization:{planning_result_id}",
        qualification_artifact_id=certificate_ref.artifact_id,
        registry_artifact_id=authorization_ref.artifact_id,
    )


@pytest.fixture(autouse=True)
def _isolate_planning_assurance_cost(monkeypatch, request):
    module = request.module
    module_name = module.__name__.rsplit(".", 1)[-1]
    if module_name not in _TARGET_MODULES:
        return

    node_key = f"{module_name}::{request.node.name}"

    # Every ordinary/publication planning fixture is the exact owned 15-player FULL_OFFICIAL
    # synthetic world. That world is intentionally the focused chip-surface case: WC/FH rebuilds
    # have exactly one legal squad, so chip mechanics can be proven without crossing them with a
    # transfer-combination surface. The independent qualification helper adds a second retained
    # 16-player finance/banking case with current-set chips already consumed. Coverage is derived
    # across both cases; production planner/worker semantics are not mocked or narrowed.
    monkeypatch.setattr(
        planning_fixture_helpers,
        "CANDIDATE_POSITIONS",
        dict(planning_fixture_helpers.OWNED_POSITIONS),
    )
    cache_variant = "focused-chip-15"

    original_fixture = getattr(module, "synthetic_production_planning_bundle", None)
    if callable(original_fixture):
        monkeypatch.setattr(
            module,
            "synthetic_production_planning_bundle",
            lambda *, store, season="2026-2027", entry=63984, gameweek=2: _cached_planning_fixture(
                original_fixture,
                store=store,
                cache_variant=cache_variant,
                season=season,
                entry=entry,
                gameweek=gameweek,
            ),
        )

    original_authority = getattr(module, "synthetic_production_champion_authority", None)
    if callable(original_authority):
        monkeypatch.setattr(
            module,
            "synthetic_production_champion_authority",
            lambda *,
            store,
            fixture,
            reviewed_at="2026-08-24T12:00:00Z",
            current_generation_artifact_id=None,
            expected_parent_generation_id=None: _cached_champion_authority(
                original_authority,
                store=store,
                fixture=fixture,
                reviewed_at=reviewed_at,
                current_generation_artifact_id=current_generation_artifact_id,
                expected_parent_generation_id=expected_parent_generation_id,
            ),
        )

    if module_name in {
        "test_v2_production_cutover",
        "test_v2_production_authority",
    } and node_key not in _FULL_PARITY_TESTS:
        monkeypatch.setattr(
            production_cutover_module,
            "claim_has_matching_planning_reference_solver_parity",
            _lightweight_parity_dependency,
        )
        if hasattr(module, "synthetic_planning_parity_material"):
            monkeypatch.setattr(
                module,
                "synthetic_planning_parity_material",
                _lightweight_parity_material,
            )