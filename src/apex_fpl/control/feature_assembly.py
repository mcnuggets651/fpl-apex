"""Assemble one FeatureSnapshot from cutoff-valid sealed inputs only."""

from __future__ import annotations

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.feature_batch import load_feature_batch
from apex_fpl.control.feature_snapshot import StoredFeatureSnapshot, build_and_store_feature_snapshot
from apex_fpl.control.official_features import official_player_feature_observations


def assemble_feature_snapshot(
    *,
    season: str,
    cutoff: str,
    global_world_manifest_artifact_id: str,
    feature_batch_artifact_ids: tuple[str, ...] = (),
    store: ArtifactStore,
) -> StoredFeatureSnapshot:
    """Build a point-in-time feature snapshot without network or wall-clock access.

    Duplicate canonical feature keys across producers fail in the FeatureSnapshot
    constructor. Apex never resolves conflicting derived features by input order.
    """

    world_id, official, official_inputs = official_player_feature_observations(
        global_world_manifest_artifact_id=global_world_manifest_artifact_id,
        cutoff=cutoff,
        store=store,
    )
    observations = list(official)
    inputs = set(official_inputs)
    for artifact_id in feature_batch_artifact_ids:
        batch = load_feature_batch(artifact_id, cutoff=cutoff, store=store)
        observations.extend(batch.batch.observations)
        inputs.add(batch.artifact_id)
        inputs.update(batch.batch.source_artifact_ids)
    return build_and_store_feature_snapshot(
        season=season,
        cutoff=cutoff,
        global_world_id=world_id,
        observations=tuple(observations),
        input_artifact_ids=tuple(sorted(inputs)),
        store=store,
    )
