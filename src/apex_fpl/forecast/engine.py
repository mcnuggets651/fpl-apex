"""Compile an immutable model prediction batch into one sealed probabilistic forecast."""

from __future__ import annotations

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.feature_snapshot import load_feature_snapshot
from apex_fpl.control.forecast_model_registry import ForecastModelRegistry
from apex_fpl.core.forecast import ForecastUseMode, compile_forecast
from apex_fpl.core.rules import RuleSet

from .forecast_store import StoredForecast, store_forecast
from .prediction_store import load_prediction_batch
from .targets import build_official_forecast_targets


def compile_sealed_forecast(
    *,
    feature_snapshot_artifact_id: str,
    prediction_batch_artifact_id: str,
    global_world_manifest_artifact_id: str,
    ruleset: RuleSet,
    model_registry: ForecastModelRegistry,
    use_mode: ForecastUseMode,
    store: ArtifactStore,
) -> StoredForecast:
    """Compile a forecast using only sealed artifacts and explicit registry state.

    This function has no transport, clock or mutable-source port. Production compilation
    additionally requires the registered champion, verified parameter/qualification
    artifacts and complete predictions for the exact Official player-fixture universe.
    """

    stored_features = load_feature_snapshot(feature_snapshot_artifact_id, store=store)
    stored_predictions = load_prediction_batch(prediction_batch_artifact_id, store=store)
    snapshot = stored_features.snapshot
    batch = stored_predictions.batch

    if batch.feature_snapshot_id != snapshot.snapshot_id:
        raise ValueError("prediction batch FeatureSnapshotId does not match sealed snapshot")
    if batch.feature_cutoff != snapshot.cutoff:
        raise ValueError("prediction batch cutoff does not match sealed FeatureSnapshot cutoff")
    if batch.global_world_id != snapshot.global_world_id:
        raise ValueError("prediction batch GlobalWorldId does not match sealed FeatureSnapshot")
    if batch.season != snapshot.season or ruleset.season != snapshot.season:
        raise ValueError("forecast season is inconsistent across snapshot, batch and RuleSet")

    model = model_registry.get(batch.model_artifact_id)
    if model is None:
        raise ValueError("prediction batch references an unregistered forecast model")
    production = use_mode is ForecastUseMode.PRODUCTION
    model_registry.verify_model_artifacts(model, store=store, production=production)

    target_set = build_official_forecast_targets(
        global_world_manifest_artifact_id=global_world_manifest_artifact_id,
        feature_snapshot=snapshot,
        gameweeks=batch.gameweeks,
        store=store,
    )
    forecast = compile_forecast(
        prediction_batch=batch,
        ruleset=ruleset,
        model=model,
        use_mode=use_mode,
        expected_targets=target_set.targets,
    )
    if production and forecast.abstentions:
        raise ValueError(
            "production forecast cannot omit/abstain from Official player-fixture targets"
        )
    return store_forecast(forecast, store=store)
