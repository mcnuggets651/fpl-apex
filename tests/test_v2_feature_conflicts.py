from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.core.features import FeatureObservation, FeatureScope, FeatureSnapshot, FeatureValue, FeatureValueKind
from apex_fpl.core.ids import GlobalWorldId


def test_conflicting_feature_producers_fail_instead_of_last_write_wins(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    source_a = store.put_bytes(b"producer-a").artifact_id
    source_b = store.put_bytes(b"producer-b").artifact_id
    first = FeatureObservation(
        feature_name="preseason.minutes",
        scope=FeatureScope.PLAYER,
        entity_id="1",
        value=FeatureValue(kind=FeatureValueKind.INTEGER, integer_value=45, unit="minutes"),
        observed_at="2026-08-20T18:00:00Z",
        first_known_at="2026-08-20T20:00:00Z",
        source_artifact_ids=(source_a,),
        derivation_id="producer-a.v1",
    )
    conflicting = FeatureObservation(
        feature_name="preseason.minutes",
        scope=FeatureScope.PLAYER,
        entity_id="1",
        value=FeatureValue(kind=FeatureValueKind.INTEGER, integer_value=90, unit="minutes"),
        observed_at="2026-08-20T18:00:00Z",
        first_known_at="2026-08-20T20:00:00Z",
        source_artifact_ids=(source_b,),
        derivation_id="producer-b.v1",
    )
    with pytest.raises(ValueError, match="duplicate canonical feature keys"):
        FeatureSnapshot(
            season="2026-2027",
            cutoff="2026-08-24T06:00:00Z",
            global_world_id=GlobalWorldId("world"),
            observations=(first, conflicting),
            input_artifact_ids=(source_a, source_b),
        )
