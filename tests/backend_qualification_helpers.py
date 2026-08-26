"""Synthetic backend qualification fixtures for mechanism tests only.

Nothing created here is real production deployment evidence. The helpers exercise the exact
production contracts inside isolated temporary stores so tests can prove publication/replay
mechanics without fabricating a real deployed backend outside the test process.
"""

from __future__ import annotations

from uuid import uuid4

from apex_fpl.control.backend_operational_qualification import (
    derive_backend_qualification_from_probes,
    derive_production_backend_qualification,
    store_backend_deployment_evidence_item,
    store_backend_deployment_qualification_evidence,
)
from apex_fpl.core.backend_qualification import (
    REQUIRED_BACKEND_DEPLOYMENT_EVIDENCE_KINDS,
    BackendDeploymentQualificationEvidence,
)


def synthetic_production_backend_qualification(
    *,
    store,
    registry,
    qualification_scope: str,
    environment_class: str = "PRODUCTION",
):
    """Build fully typed synthetic evidence for isolated contract tests."""

    nonce = uuid4().hex
    mechanical = derive_backend_qualification_from_probes(
        artifact_store=store,
        release_registry=registry,
        qualification_scope=qualification_scope,
        probe_nonce=nonce,
    )
    deployment_id = f"synthetic-test-deployment:{nonce}"
    items = []
    for kind in sorted(REQUIRED_BACKEND_DEPLOYMENT_EVIDENCE_KINDS):
        source = store.put_bytes(
            f"synthetic-test-only:{deployment_id}:{kind}".encode("utf-8")
        ).artifact_id
        items.append(
            store_backend_deployment_evidence_item(
                store=store,
                artifact_store_backend_id=mechanical.artifact_store_evidence.backend_id,
                release_registry_backend_id=mechanical.release_registry_evidence.backend_id,
                qualification_scope=qualification_scope,
                deployment_id=deployment_id,
                evidence_kind=kind,
                issuer="synthetic-test-fixture",
                observed_at="2026-08-25T05:00:00Z",
                outcome="PASS",
                source_artifact_ids=(source,),
            )
        )
    deployment = BackendDeploymentQualificationEvidence(
        artifact_store_backend_id=mechanical.artifact_store_evidence.backend_id,
        release_registry_backend_id=mechanical.release_registry_evidence.backend_id,
        qualification_scope=qualification_scope,
        deployment_id=deployment_id,
        environment_class=environment_class,
        evaluated_at="2026-08-25T05:30:00Z",
        evidence_items=tuple(items),
    )
    deployment_artifact_id = store_backend_deployment_qualification_evidence(
        deployment,
        store=store,
    )
    return derive_production_backend_qualification(
        mechanical,
        deployment_evidence_artifact_id=deployment_artifact_id,
        store=store,
    )
