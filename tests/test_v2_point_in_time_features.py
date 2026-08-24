from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from apex_fpl.acquisition import (
    FPL_BOOTSTRAP_URL,
    FPL_FIXTURES_URL,
    HttpResponse,
    acquire_official_global_world,
)
from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.feature_snapshot import (
    build_and_store_feature_snapshot,
    load_feature_snapshot,
)
from apex_fpl.control.official_features import official_player_feature_observations
from apex_fpl.control.outcome_truth_registry import load_outcome_truth_registry
from apex_fpl.core.features import (
    FeatureObservation,
    FeatureScope,
    FeatureSnapshot,
    FeatureValue,
    FeatureValueKind,
)
from apex_fpl.core.ids import GlobalWorldId
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.minutes_features import minutes_feature_vector
from apex_fpl.core.outcome_truth import OutcomeTarget, TruthAuthorityStatus


FIXTURES = [{"id": 10, "team_h": 1, "team_a": 2, "event": 1}]


def _bootstrap(*, price: int = 55, minutes: int = 0, starts: int = 0, chance=None):
    return {
        "elements": [
            {
                "id": 1,
                "element_type": 3,
                "team": 1,
                "now_cost": price,
                "status": "a",
                "chance_of_playing_next_round": chance,
                "minutes": minutes,
                "starts": starts,
            },
            {
                "id": 2,
                "element_type": 4,
                "team": 2,
                "now_cost": 70,
                "status": "a",
                "chance_of_playing_next_round": 100,
                "minutes": 90,
                "starts": 1,
            },
        ],
        "teams": [{"id": 1, "name": "Alpha"}, {"id": 2, "name": "Beta"}],
        "events": [{"id": 1, "deadline_time": "2026-08-21T17:30:00Z"}],
    }


def _bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class FixedClock:
    def __init__(self, stamp: datetime):
        self.stamp = stamp

    def now(self) -> datetime:
        return self.stamp


class FakeTransport:
    def __init__(self, bootstrap):
        self.payloads = {
            FPL_BOOTSTRAP_URL: _bytes(bootstrap),
            FPL_FIXTURES_URL: _bytes(FIXTURES),
        }

    def get(self, url: str, *, params: dict[str, str]) -> HttpResponse:
        assert params == {}
        return HttpResponse(
            status_code=200,
            body=self.payloads[url],
            headers={"Content-Type": "application/json", "ETag": '"pit"'},
        )


def _artifact(store: FileSystemArtifactStore, value: bytes = b"input") -> str:
    return store.put_bytes(value).artifact_id


def _obs(
    artifact: str,
    *,
    name: str = "sample",
    entity: str = "1",
    value: FeatureValue | None = None,
    observed: str = "2026-08-24T04:00:00Z",
    known: str = "2026-08-24T05:00:00Z",
) -> FeatureObservation:
    return FeatureObservation(
        feature_name=name,
        scope=FeatureScope.PLAYER,
        entity_id=entity,
        value=value
        or FeatureValue(kind=FeatureValueKind.INTEGER, integer_value=1, unit="count"),
        observed_at=observed,
        first_known_at=known,
        source_artifact_ids=(artifact,),
        derivation_id="test.direct.v1",
    )


def test_feature_snapshot_rejects_any_feature_first_known_after_cutoff(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    artifact = _artifact(store)
    future = _obs(artifact, known="2026-08-24T06:00:01Z")
    with pytest.raises(ValueError, match="first known after snapshot cutoff"):
        FeatureSnapshot(
            season="2026-2027",
            cutoff="2026-08-24T06:00:00Z",
            global_world_id=GlobalWorldId("world"),
            observations=(future,),
            input_artifact_ids=(artifact,),
        )


def test_feature_snapshot_records_exact_cutoff_lineage_and_replays_offline(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    artifact_a = _artifact(store, b"a")
    artifact_b = _artifact(store, b"b")
    one = _obs(artifact_a, name="one")
    two = _obs(artifact_b, name="two")
    stored = build_and_store_feature_snapshot(
        season="2026-2027",
        cutoff="2026-08-24T06:00:00Z",
        global_world_id=GlobalWorldId("world"),
        observations=(two, one),
        input_artifact_ids=(artifact_b, artifact_a),
        store=store,
    )
    replay = load_feature_snapshot(stored.artifact_id, store=store)
    assert replay.snapshot.snapshot_id == stored.snapshot.snapshot_id
    assert replay.snapshot.cutoff == "2026-08-24T06:00:00Z"
    assert replay.snapshot.input_artifact_ids == tuple(sorted((artifact_a, artifact_b)))
    assert [row.feature_name for row in replay.snapshot.observations] == ["one", "two"]


def test_missing_feature_is_not_zero_and_changes_semantic_identity(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    artifact = _artifact(store)
    missing = _obs(
        artifact,
        name="preseason.minutes",
        value=FeatureValue(kind=FeatureValueKind.MISSING, missing_reason="not observed"),
    )
    zero = _obs(
        artifact,
        name="preseason.minutes",
        value=FeatureValue(kind=FeatureValueKind.INTEGER, integer_value=0, unit="minutes"),
    )
    assert missing.observation_id != zero.observation_id
    assert missing.value.integer_value is None


def test_later_official_world_cannot_leak_into_earlier_feature_cutoff(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    early = acquire_official_global_world(
        season="2026-2027",
        transport=FakeTransport(_bootstrap(price=55, minutes=0, starts=0)),
        clock=FixedClock(datetime(2026, 8, 24, 5, tzinfo=timezone.utc)),
        store=store,
    )
    late = acquire_official_global_world(
        season="2026-2027",
        transport=FakeTransport(_bootstrap(price=56, minutes=90, starts=1)),
        clock=FixedClock(datetime(2026, 8, 24, 7, tzinfo=timezone.utc)),
        store=store,
    )
    _, early_rows, _ = official_player_feature_observations(
        global_world_manifest_artifact_id=early.manifest_artifact_id,
        cutoff="2026-08-24T06:00:00Z",
        store=store,
    )
    price = next(
        row
        for row in early_rows
        if row.entity_id == "1" and row.feature_name == "official.price_tenths"
    )
    assert price.value.integer_value == 55
    with pytest.raises(ValueError, match="retrieved after feature cutoff"):
        official_player_feature_observations(
            global_world_manifest_artifact_id=late.manifest_artifact_id,
            cutoff="2026-08-24T06:00:00Z",
            store=store,
        )


def test_official_null_chance_remains_missing_not_assumed_available(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    sealed = acquire_official_global_world(
        season="2026-2027",
        transport=FakeTransport(_bootstrap(chance=None)),
        clock=FixedClock(datetime(2026, 8, 24, 5, tzinfo=timezone.utc)),
        store=store,
    )
    world_id, rows, inputs = official_player_feature_observations(
        global_world_manifest_artifact_id=sealed.manifest_artifact_id,
        cutoff="2026-08-24T06:00:00Z",
        store=store,
    )
    chance = next(
        row
        for row in rows
        if row.entity_id == "1" and row.feature_name == "official.chance_next_round_bps"
    )
    assert chance.value.kind is FeatureValueKind.MISSING
    assert chance.value.integer_value is None
    assert world_id == sealed.world.world_id
    assert sealed.manifest_artifact_id in inputs


def test_minutes_vector_has_no_implicit_prior_or_preseason_defaults(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    artifact = _artifact(store)
    rows = (
        _obs(
            artifact,
            name="official.cumulative_minutes",
            value=FeatureValue(kind=FeatureValueKind.INTEGER, integer_value=0, unit="minutes"),
        ),
        _obs(
            artifact,
            name="official.cumulative_starts",
            value=FeatureValue(kind=FeatureValueKind.INTEGER, integer_value=0, unit="starts"),
        ),
        _obs(
            artifact,
            name="official.status",
            value=FeatureValue(kind=FeatureValueKind.CATEGORICAL, categorical_value="a"),
        ),
    )
    snapshot = FeatureSnapshot(
        season="2026-2027",
        cutoff="2026-08-24T06:00:00Z",
        global_world_id=GlobalWorldId("world"),
        observations=rows,
        input_artifact_ids=(artifact,),
    )
    vector = minutes_feature_vector(snapshot, OfficialPlayerId(1))
    assert vector.current_cumulative_minutes == 0
    assert vector.prior_minutes is None
    assert vector.preseason_minutes is None
    assert "history.prior_minutes" in vector.missing_features
    assert "preseason.minutes" in vector.missing_features
    assert not hasattr(vector, "expected_minutes")


def test_isolated_preseason_cameo_is_preserved_beside_mature_history_not_blended_over_it(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    artifact = _artifact(store)
    numeric = {
        "history.prior_minutes": (2700, "minutes"),
        "history.prior_starts": (30, "starts"),
        "history.prior_appearances": (32, "appearances"),
        "preseason.minutes": (45, "minutes"),
        "preseason.starts": (0, "starts"),
        "preseason.appearances": (1, "appearances"),
    }
    rows = tuple(
        _obs(
            artifact,
            name=name,
            value=FeatureValue(kind=FeatureValueKind.INTEGER, integer_value=value, unit=unit),
        )
        for name, (value, unit) in numeric.items()
    )
    snapshot = FeatureSnapshot(
        season="2026-2027",
        cutoff="2026-08-24T06:00:00Z",
        global_world_id=GlobalWorldId("world"),
        observations=rows,
        input_artifact_ids=(artifact,),
    )
    vector = minutes_feature_vector(snapshot, OfficialPlayerId(1))
    assert vector.prior_minutes == 2700
    assert vector.preseason_minutes == 45
    assert vector.isolated_preseason_cameo is True
    assert not hasattr(vector, "expected_minutes")


def test_outcome_truth_registry_never_silently_selects_unverified_truth_provider():
    registry = load_outcome_truth_registry(Path("config/outcome_truth_v2.yaml"))
    assert len(registry.authorities) == len(OutcomeTarget)
    assert registry.authority_for(OutcomeTarget.FPL_POINTS).status is TruthAuthorityStatus.VERIFIED
    assert registry.authority_for(OutcomeTarget.MINUTES).status is TruthAuthorityStatus.VERIFIED
    assert registry.authority_for(OutcomeTarget.PRICE).status is TruthAuthorityStatus.VERIFIED
    assert registry.authority_for(OutcomeTarget.START).status is TruthAuthorityStatus.UNRESOLVED
    assert registry.authority_for(OutcomeTarget.LINEUP).status is TruthAuthorityStatus.UNRESOLVED
    assert registry.authority_for(OutcomeTarget.UNDERLYING_XG).status is TruthAuthorityStatus.UNRESOLVED
    assert registry.authority_for(OutcomeTarget.UNDERLYING_XA).status is TruthAuthorityStatus.UNRESOLVED
