"""Runtime evaluation for one registered source capability."""

from __future__ import annotations

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.source_registry import RegisteredSourceCapability, SourceRegistry
from apex_fpl.core.sources import (
    DegradationDecision,
    SourceAdmissionState,
    SourceHealth,
    evaluate_source_runtime,
)


def evaluate_registered_source(
    registered: RegisteredSourceCapability,
    health: SourceHealth,
    *,
    registry: SourceRegistry,
    store: ArtifactStore,
) -> DegradationDecision:
    """Evaluate health only against verified admission/degradation evidence."""

    if registered.capability.admission_state is SourceAdmissionState.QUALIFIED:
        artifact = registered.qualification_artifact_id
        if artifact is None or not store.verify(artifact):
            return DegradationDecision.BLOCKED
    degradation = registry.degradation_for(registered.capability.capability)
    if degradation is not None and not store.verify(degradation.validation_artifact_id):
        degradation = None
    return evaluate_source_runtime(
        registered.capability,
        health,
        degradation=degradation,
    )
