from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.feature_batch import FeatureBatch, load_feature_batch, store_feature_batch
from apex_fpl.core.features import FeatureObservation, FeatureScope, FeatureValue, FeatureValueKind
from apex_fpl.core.identity import OfficialPlayerId, PersonLink
from apex_fpl.core.ids import PersonId
from apex_fpl.core.minutes_history import (
    HistoricalMinutesSample,
    PreseasonAppearance,
    historical_minutes_observations,
    preseason_minutes_observations,
)


def _artifact(store: FileSystemArtifactStore, body: bytes = b"source") -> str:
    return store.put_bytes(body).artifact_id


def _observation(artifact: str, *, known: str = "2026-08-24T05:00:00Z") -> FeatureObservation:
    return FeatureObservation(
        feature_name="preseason.minutes",
        scope=FeatureScope.PLAYER,
        entity_id="1",
        value=FeatureValue(kind=FeatureValueKind.INTEGER, integer_value=45, unit="minutes"),
        observed_at="2026-08-24T04:00:00Z",
        first_known_at=known,
        source_artifact_ids=(artifact,),
        derivation_id="test.batch.v1",
    )


def test_feature_batch_cannot_claim_availability_before_its_latest_observation(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    artifact = _artifact(store)
    with pytest.raises(ValueError, match="first-known after its batch availability"):
        FeatureBatch(
            batch_kind="preseason",
            available_at="2026-08-24T04:59:59Z",
            observations=(_observation(artifact),),
            source_artifact_ids=(artifact,),
            producer_id="test",
        )


def test_later_derived_feature_batch_cannot_be_used_at_earlier_cutoff(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    artifact = _artifact(store)
    batch = FeatureBatch(
        batch_kind="preseason",
        available_at="2026-08-24T06:30:00Z",
        observations=(_observation(artifact, known="2026-08-24T06:00:00Z"),),
        source_artifact_ids=(artifact,),
        producer_id="test",
    )
    stored = store_feature_batch(batch, store=store)
    with pytest.raises(ValueError, match="not available at requested cutoff"):
        load_feature_batch(
            stored.artifact_id,
            cutoff="2026-08-24T06:00:00Z",
            store=store,
        )
    replay = load_feature_batch(
        stored.artifact_id,
        cutoff="2026-08-24T07:00:00Z",
        store=store,
    )
    assert replay.batch.batch_id == batch.batch_id


def test_prior_season_minutes_require_reviewed_person_link_not_name_or_old_id(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    artifact = _artifact(store)
    sample = HistoricalMinutesSample(
        person_id=PersonId("person-one"),
        season="2025-2026",
        minutes=2700,
        starts=30,
        appearances=32,
        observed_at="2026-05-25T18:00:00Z",
        first_known_at="2026-05-26T08:00:00Z",
        source_artifact_id=artifact,
    )
    wrong_link = PersonLink(
        person_id=PersonId("different-person"),
        player_id=OfficialPlayerId(1),
        source_reference="reviewed-link-artifact",
    )
    with pytest.raises(ValueError, match="PersonId does not match"):
        historical_minutes_observations(
            sample,
            current_link=wrong_link,
            cutoff="2026-08-24T06:00:00Z",
        )
    link = PersonLink(
        person_id=PersonId("person-one"),
        player_id=OfficialPlayerId(7),
        source_reference="reviewed-link-artifact",
    )
    rows = historical_minutes_observations(
        sample,
        current_link=link,
        cutoff="2026-08-24T06:00:00Z",
    )
    assert {row.entity_id for row in rows} == {"7"}
    assert {row.feature_name for row in rows} == {
        "history.prior_minutes",
        "history.prior_starts",
        "history.prior_appearances",
    }


def test_historical_sample_first_known_after_cutoff_is_rejected(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    artifact = _artifact(store)
    sample = HistoricalMinutesSample(
        person_id=PersonId("person-one"),
        season="2025-2026",
        minutes=100,
        starts=1,
        appearances=2,
        observed_at="2026-05-25T18:00:00Z",
        first_known_at="2026-08-25T08:00:00Z",
        source_artifact_id=artifact,
    )
    link = PersonLink(
        person_id=PersonId("person-one"),
        player_id=OfficialPlayerId(1),
        source_reference="reviewed-link-artifact",
    )
    with pytest.raises(ValueError, match="not known by feature cutoff"):
        historical_minutes_observations(
            sample,
            current_link=link,
            cutoff="2026-08-24T06:00:00Z",
        )


def test_preseason_aggregation_excludes_appearance_first_known_after_cutoff(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    early_artifact = _artifact(store, b"early")
    future_artifact = _artifact(store, b"future")
    player = OfficialPlayerId(1)
    early = PreseasonAppearance(
        player_id=player,
        match_at="2026-08-20T18:00:00Z",
        minutes=45,
        started=False,
        first_known_at="2026-08-20T20:00:00Z",
        source_artifact_id=early_artifact,
    )
    future = PreseasonAppearance(
        player_id=player,
        match_at="2026-08-24T05:30:00Z",
        minutes=90,
        started=True,
        first_known_at="2026-08-24T06:30:00Z",
        source_artifact_id=future_artifact,
    )
    rows = preseason_minutes_observations(
        player,
        (early, future),
        cutoff="2026-08-24T06:00:00Z",
    )
    by_name = {row.feature_name: row for row in rows}
    assert by_name["preseason.minutes"].value.integer_value == 45
    assert by_name["preseason.starts"].value.integer_value == 0
    assert by_name["preseason.appearances"].value.integer_value == 1
    assert by_name["preseason.latest_appearance_started"].value.boolean_value is False
    assert future_artifact not in by_name["preseason.minutes"].source_artifact_ids


def test_preseason_aggregation_preserves_repeated_starts_without_subjective_final_friendly_flag(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    player = OfficialPlayerId(1)
    rows = preseason_minutes_observations(
        player,
        tuple(
            PreseasonAppearance(
                player_id=player,
                match_at=f"2026-08-{day:02d}T18:00:00Z",
                minutes=90,
                started=True,
                first_known_at=f"2026-08-{day:02d}T20:00:00Z",
                source_artifact_id=_artifact(store, f"match-{day}".encode()),
            )
            for day in (10, 15, 20)
        ),
        cutoff="2026-08-24T06:00:00Z",
    )
    by_name = {row.feature_name: row for row in rows}
    assert by_name["preseason.starts"].value.integer_value == 3
    assert by_name["preseason.appearances"].value.integer_value == 3
    assert by_name["preseason.consecutive_recent_starts"].value.integer_value == 3
    assert by_name["preseason.latest_appearance_started"].value.boolean_value is True
