"""Store and replay the typed Apex V2 production artifact closure."""

from __future__ import annotations

import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.artifact_manifest import (
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactManifestRole,
)
from apex_fpl.core.canonical import canonical_json_bytes


def _strict_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def store_artifact_manifest(manifest: ArtifactManifest, *, store: ArtifactStore) -> str:
    """Persist one self-addressing canonical release closure."""

    content = canonical_json_bytes(manifest.semantic_payload())
    ref = store.put_bytes(
        content,
        media_type="application/json",
        schema_name="apex-artifact-manifest",
        schema_version="1",
    )
    if ref.artifact_id != manifest.manifest_id:
        raise ValueError("artifact manifest storage identity does not match semantic identity")
    return ref.artifact_id


def load_artifact_manifest(
    artifact_id: str,
    *,
    store: ArtifactStore,
    verify_members: bool = True,
) -> ArtifactManifest:
    """Strictly replay a manifest and, by default, every retained member."""

    raw_bytes = store.read_bytes(artifact_id)
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("artifact manifest is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("artifact manifest must be object")
    if canonical_json_bytes(raw) != raw_bytes:
        raise ValueError("artifact manifest must be canonical JSON")
    if raw.get("schema_name") != "apex-artifact-manifest":
        raise ValueError("not an Apex artifact manifest")
    if _strict_int(raw.get("schema_version"), label="artifact manifest schema_version") != 1:
        raise ValueError("unsupported artifact manifest schema")
    entries_raw = raw.get("entries")
    if not isinstance(entries_raw, list) or any(not isinstance(item, dict) for item in entries_raw):
        raise ValueError("artifact manifest entries must be object array")
    entries = tuple(
        ArtifactManifestEntry(
            role=ArtifactManifestRole(str(item.get("role") or "")),
            artifact_id=str(item.get("artifact_id") or ""),
            semantic_id=(
                None if item.get("semantic_id") is None else str(item.get("semantic_id"))
            ),
        )
        for item in entries_raw
    )
    manifest = ArtifactManifest(
        season=str(raw.get("season") or ""),
        entry=_strict_int(raw.get("entry"), label="artifact manifest entry"),
        gameweek=_strict_int(raw.get("gameweek"), label="artifact manifest gameweek"),
        bundle_id=str(raw.get("bundle_id") or ""),
        world_id=str(raw.get("world_id") or ""),
        runtime_digest=str(raw.get("runtime_digest") or ""),
        authority_root_artifact_id=str(raw.get("authority_root_artifact_id") or ""),
        entries=entries,
        schema_version=1,
    )
    if manifest.semantic_payload() != raw or manifest.manifest_id != artifact_id:
        raise ValueError("artifact manifest semantic identity mismatch")
    if verify_members:
        for entry in manifest.entries:
            if not store.verify(entry.artifact_id):
                raise ValueError(f"artifact manifest member is missing/corrupt: {entry.role.value}")
    return manifest


def verify_artifact_manifest_scope(
    manifest: ArtifactManifest,
    *,
    season: str,
    entry: int,
    gameweek: int,
    bundle_id: str,
    world_id: str,
    runtime_digest: str,
    authority_root_artifact_id: str,
) -> None:
    """Fail closed unless one replayed manifest matches the exact release scope."""

    expected = (
        str(season),
        entry,
        gameweek,
        str(bundle_id),
        str(world_id),
        str(runtime_digest),
        str(authority_root_artifact_id),
    )
    actual = (
        manifest.season,
        manifest.entry,
        manifest.gameweek,
        manifest.bundle_id,
        manifest.world_id,
        manifest.runtime_digest,
        manifest.authority_root_artifact_id,
    )
    if actual != expected:
        raise ValueError("artifact manifest scope does not match production release")
