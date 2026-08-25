from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pytest

import apex_fpl.control.production_cutover as production_cutover_module


PARITY_PROOF_ID = "PO-REFERENCE-SOLVER-PARITY-001"
_TARGET_MODULES = {
    "test_v2_production_cutover",
    "test_v2_production_authority",
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


_PLANNING_FIXTURE_CACHE: dict[tuple[str, int, int], _CachedPlanningFixture] = {}


def _cached_planning_fixture(
    original: Callable[..., object],
    *,
    store,
    season: str = "2026-2027",
    entry: int = 63984,
    gameweek: int = 2,
):
    """Reuse exact synthetic lineage bytes across isolated cutover/authority test stores.

    The first call executes the real planner and records every immutable artifact write. Later
    calls restore the same content-addressed bytes into each test's own ArtifactStore. This is a
    test-fixture optimization only; production planning-result/bundle/qualification replay is not
    bypassed or cached.
    """

    key = (str(season), int(entry), int(gameweek))
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


@pytest.fixture(autouse=True)
def _isolate_planning_assurance_cost(monkeypatch, request):
    module = request.module
    module_name = module.__name__.rsplit(".", 1)[-1]
    if module_name not in _TARGET_MODULES:
        return

    original_fixture = getattr(module, "synthetic_production_planning_bundle", None)
    if callable(original_fixture):
        monkeypatch.setattr(
            module,
            "synthetic_production_planning_bundle",
            lambda *, store, season="2026-2027", entry=63984, gameweek=2: _cached_planning_fixture(
                original_fixture,
                store=store,
                season=season,
                entry=entry,
                gameweek=gameweek,
            ),
        )

    node_key = f"{module_name}::{request.node.name}"
    if node_key not in _FULL_PARITY_TESTS:
        monkeypatch.setattr(
            production_cutover_module,
            "claim_has_matching_planning_reference_solver_parity",
            _lightweight_parity_dependency,
        )
