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
    "test_v2_production_cutover",
    "test_v2_production_authority",
    "test_v2_production_planning_bundle",
    "test_v2_reference_solver_planning",
    "test_v2_reference_solver_planning_qualification",
}
_STRONG_FIXTURE_MODULES = {
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


def _cached_planning_fixture(
    original: Callable[..., object],
    *,
    store,
    cache_variant: str,
    season: str = "2026-2027",
    entry: int = 63984,
    gameweek: int = 2,
):
    """Reuse exact synthetic lineage bytes across isolated assurance-test stores.

    The first call for each semantic fixture variant executes the real planner and records every
    immutable artifact write. Later calls restore those exact content-addressed bytes into each
    test's isolated ArtifactStore. Production planning-result, bundle, qualification and
    authorization replay are never cached or bypassed by this helper.
    """

    key = (cache_variant, str(season), int(entry), int(gameweek))
    cached = _PLANNING_FIXTURE_CACHE.get(key)
    if cached is not None:
        for item in cached.artifacts:
            ref = store.put_bytes(item.content, **dict(item.kwargs))
            if ref.artifact_id != item.artifact_id:
                raise ValueError("cached synthetic planning fixture artifact identity drifted")
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


def _lightweight_parity_dependency(claim, *, verified_bundle, store) -> bool:
    """Unit-test seam for tests whose subject is not solver parity.

    Dedicated end-to-end tests leave the real replay path untouched. This seam still requires the
    exact bundle PlanningResultId to be present in the parity claim so unrelated proof evidence
    cannot accidentally satisfy the dependency in isolated tests.
    """

    del store
    return (
        claim.proof_id == PARITY_PROOF_ID
        and str(verified_bundle.decision.planning_result_id) in set(claim.evidence_ids)
    )


def _lightweight_parity_material(*, store, fixture) -> SyntheticPlanningParityMaterial:
    """Build only immutable parity claim material for tests unrelated to parity replay.

    These tests deliberately use the 15-player lineage-only fixture, which cannot and must not
    satisfy the strong worker qualification corpus requiring an executed transfer-finance case.
    The production parity validator is independently replaced by ``_lightweight_parity_dependency``
    for the same tests, while every dedicated parity test continues to execute the full sealed
    worker/corpus/qualification/champion/certificate path.
    """

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
    requires_strong_fixture = (
        module_name in _STRONG_FIXTURE_MODULES or node_key in _FULL_PARITY_TESTS
    )

    # Most production-control tests exercise bundle/CAS/expiry/authority semantics, not transfer
    # search breadth. For those tests the synthetic FULL_OFFICIAL universe is exactly the owned
    # 15-player squad, which keeps the real two-GW planner/replay path but removes irrelevant
    # transfer combinatorics. Dedicated parity/worker/qualification tests retain the stronger
    # 16-player banking, finance and terminal-chip-reserve world. Both fixture variants are built
    # by the real planner once and then restored byte-for-byte into isolated ArtifactStores.
    cache_variant = "strong-parity" if requires_strong_fixture else "lineage-only"
    if not requires_strong_fixture:
        monkeypatch.setattr(
            planning_fixture_helpers,
            "CANDIDATE_POSITIONS",
            dict(planning_fixture_helpers.OWNED_POSITIONS),
        )

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
