"""Non-actionable V2 shadow release-path rehearsal for Slice 12."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterable, Protocol

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.release_registry import (
    FileSystemReleaseRegistry,
    ReleaseKey,
    ReleaseRecord,
    ReleaseStatus,
)
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.ids import BundleId, GlobalWorldId, ReleaseId
from apex_fpl.core.proofs import AssuranceCase, ProofObligation
from apex_fpl.core.shadow import ShadowProductionReport, ShadowProductionStatus


class CurrentReleaseReader(Protocol):
    """Read-only production release surface available to shadow execution."""

    def current_release_id(self, key: ReleaseKey) -> str | None: ...


@dataclass(frozen=True, slots=True)
class ShadowProductionOutcome:
    report: ShadowProductionReport
    report_artifact_id: str
    release_record: ReleaseRecord


def _verify_artifact(store: ArtifactStore, artifact_id: str, *, label: str) -> str:
    value = str(artifact_id).strip()
    if not value:
        raise ValueError(f"{label} artifact ID is required")
    if not store.verify(value):
        raise ValueError(f"{label} artifact missing/corrupt: {value}")
    return value


def _claim_artifacts(case: AssuranceCase, store: ArtifactStore) -> tuple[str, ...]:
    artifact_ids = tuple(
        sorted({artifact for claim in case.claims for artifact in claim.artifact_ids})
    )
    for artifact_id in artifact_ids:
        _verify_artifact(store, artifact_id, label="assurance claim")
    return artifact_ids


def execute_shadow_production(
    *,
    season: str,
    entry: int,
    gameweek: int,
    bundle_id: BundleId | None,
    world_id: GlobalWorldId | None,
    runtime_digest: str,
    created_at: str,
    valid_until: str | None,
    artifact_manifest_id: str,
    assurance_case: AssuranceCase,
    obligations: Iterable[ProofObligation],
    artifact_store: ArtifactStore,
    shadow_registry: FileSystemReleaseRegistry,
    production_reader: CurrentReleaseReader,
) -> ShadowProductionOutcome:
    """Exercise the real release contract without ever publishing an actionable release."""

    if isinstance(entry, bool) or not isinstance(entry, int) or entry <= 0:
        raise ValueError("shadow entry must be positive integer")
    if isinstance(gameweek, bool) or not isinstance(gameweek, int) or gameweek <= 0:
        raise ValueError("shadow gameweek must be positive integer")
    runtime_digest = str(runtime_digest).strip()
    created_at = str(created_at).strip()
    if not runtime_digest or not created_at:
        raise ValueError("shadow runtime_digest and created_at are required")

    manifest_id = _verify_artifact(
        artifact_store,
        artifact_manifest_id,
        label="shadow artifact manifest",
    )
    claim_artifacts = _claim_artifacts(assurance_case, artifact_store)
    certificate = assurance_case.derive_release_certificate(tuple(obligations))

    key = ReleaseKey(season, entry, gameweek)
    production_before = production_reader.current_release_id(key)
    shadow_before = shadow_registry.current_release_id(key)

    record = ReleaseRecord(
        season=season,
        entry=entry,
        gameweek=gameweek,
        bundle_id=None if bundle_id is None else str(bundle_id),
        world_id=None if world_id is None else str(world_id),
        runtime_digest=runtime_digest,
        created_at=created_at,
        valid_until=valid_until,
        status=ReleaseStatus.CERTIFIED if certificate.eligible else ReleaseStatus.WITHHELD,
        ready_to_act=False,
        safe_to_act=False,
        artifact_manifest_id=manifest_id,
    )
    record = shadow_registry.append(record)
    if record.release_id is None:  # pragma: no cover - append always normalizes
        raise RuntimeError("shadow release registry did not assign release_id")
    shadow_registry.compare_and_swap_current(
        key,
        expected_release_id=shadow_before,
        new_release_id=record.release_id,
    )
    shadow_after = shadow_registry.current_release_id(key)
    production_after = production_reader.current_release_id(key)

    sources = tuple(sorted({manifest_id, *claim_artifacts}))
    report = ShadowProductionReport(
        season=season,
        entry=entry,
        gameweek=gameweek,
        bundle_id=bundle_id,
        world_id=world_id,
        release_id=ReleaseId(record.release_id),
        assurance_case_id=certificate.assurance_case_id,
        release_certificate_status=certificate.status,
        release_certificate_blockers=certificate.blockers,
        production_pointer_before=production_before,
        production_pointer_after=production_after,
        shadow_pointer_before=shadow_before,
        shadow_pointer_after=str(shadow_after),
        artifact_manifest_id=manifest_id,
        source_artifact_ids=sources,
        status=(
            ShadowProductionStatus.PASS
            if certificate.eligible
            else ShadowProductionStatus.WITHHELD
        ),
    )
    envelope = {
        "schema_name": "apex-stored-shadow-production-report",
        "schema_version": 1,
        "report_id": report.report_id,
        "payload": report.semantic_payload(),
    }
    ref = artifact_store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name="apex-stored-shadow-production-report",
        schema_version="1",
    )
    return ShadowProductionOutcome(report, ref.artifact_id, record)


def load_shadow_production_report(
    artifact_id: str,
    *,
    artifact_store: ArtifactStore,
) -> ShadowProductionReport:
    """Replay a stored shadow report and re-verify every retained source artifact."""

    try:
        raw = json.loads(artifact_store.read_bytes(artifact_id).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("shadow production report is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("stored shadow production report must be JSON object")
    if raw.get("schema_name") != "apex-stored-shadow-production-report" or raw.get("schema_version") != 1:
        raise ValueError("unsupported stored shadow production report schema")
    payload = raw.get("payload")
    report_id = raw.get("report_id")
    if not isinstance(payload, dict) or not isinstance(report_id, str):
        raise ValueError("stored shadow production report has invalid payload/identity")
    if canonical_sha256(payload) != report_id:
        raise ValueError("stored shadow production report semantic identity mismatch")

    def strict_int(value: object, *, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{label} must be integer")
        return value

    blockers = payload.get("release_certificate_blockers")
    sources = payload.get("source_artifact_ids")
    if not isinstance(blockers, list) or any(not isinstance(item, str) for item in blockers):
        raise ValueError("shadow blockers must be string array")
    if not isinstance(sources, list) or any(not isinstance(item, str) for item in sources):
        raise ValueError("shadow source artifacts must be string array")
    report = ShadowProductionReport(
        season=str(payload.get("season") or ""),
        entry=strict_int(payload.get("entry"), label="entry"),
        gameweek=strict_int(payload.get("gameweek"), label="gameweek"),
        bundle_id=(None if payload.get("bundle_id") is None else BundleId(str(payload.get("bundle_id")))),
        world_id=(None if payload.get("world_id") is None else GlobalWorldId(str(payload.get("world_id")))),
        release_id=ReleaseId(str(payload.get("release_id") or "")),
        assurance_case_id=str(payload.get("assurance_case_id") or ""),
        release_certificate_status=str(payload.get("release_certificate_status") or ""),
        release_certificate_blockers=tuple(blockers),
        production_pointer_before=(None if payload.get("production_pointer_before") is None else str(payload.get("production_pointer_before"))),
        production_pointer_after=(None if payload.get("production_pointer_after") is None else str(payload.get("production_pointer_after"))),
        shadow_pointer_before=(None if payload.get("shadow_pointer_before") is None else str(payload.get("shadow_pointer_before"))),
        shadow_pointer_after=str(payload.get("shadow_pointer_after") or ""),
        artifact_manifest_id=str(payload.get("artifact_manifest_id") or ""),
        source_artifact_ids=tuple(sources),
        status=ShadowProductionStatus(str(payload.get("status") or "")),
        schema_version=strict_int(payload.get("schema_version"), label="schema_version"),
    )
    if report.report_id != report_id:
        raise ValueError("replayed shadow production report identity mismatch")
    for source_id in report.source_artifact_ids:
        _verify_artifact(artifact_store, source_id, label="shadow replay source")
    return report
